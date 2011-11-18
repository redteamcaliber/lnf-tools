#!/usr/bin/python
#
# nfdump-tools - Inspecting the output of nfdump
#
# Copyright (C) 2011 CIRCL Computer Incident Response Center Luxembourg (smile gie)
# Copyright (C) 2011 Gerard Wagener
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import os
import sys
from kyotocabinet import *
import getopt
import time
import kindcommon
import ConfigParser

class Klookup(object):

    def __init__(self,configFile=None):
        self.configFile = configFile
        self.ipaddress = None

    def  load(self):
        try:
            self.config = ConfigParser.ConfigParser()
            if (self.configFile == None):
                raise IOError('No config file was specified')
            self.config.readfp(open(self.configFile))
            self.kco = kindcommon.KindCommon(self.config)
            p = self.config.get("indexer","dbdir")
            #Check if mandatory directories exist
            if os.path.exists(p) == False:
                raise IOError("dbdir="+ p +" does not exists ")
            self.flowdirs  = self.kco.read_flow_dirs()
        except ConfigParser.NoOptionError,e:
            sys.stderr.write("Config Error: "+str(e) + '\n')
            sys.exit(1)
        except ValueError,v:
            sys.stderr.write("Config Error: "+str(v) + '\n')
            sys.exit(1)
        except IOError,w:
            sys.stderr.write("Could not load config file "+ str(w)+"\n")
            sys.exit(1)

    def usage(self,exitcode):
        print """
Query an IP address in the collection of kyoto cabinet files

klookup [-h] -d database_directory -i IP address

OPTIONS
    -h Show this screen
    -i The IP adderss that is queries
    -c Specify the kindexer config file in order to find the absolute filenames
    -f FORMAT OPTION
    -l Loop. Klookup runs as a blocking process dedicated to run in a GNU screen
             on the system containing the databases. This process can then be queried
             via a bot for  instance an XMPP bot. The interaction is done
             via redis. (see REDIS_STRUCTURE)

The list of nfcapd files is returned corersponing to the queried IP address


FORMAT OPTIONS
    "print absolute"     Prints abolute filenames containing the IP address
    "print relative"     Print relative filenames
    check                Returns result as exit code
                            0 means that the IP addresses is known
                            1 means that the IP address is not known
    "full nfdump -r %f"  Does a full nfdump of the found occurences. After the
                         word full the nfdump tool with its argument needs to
                         be specified. %f is substituted by the filename
                         identified in the index

    "print full"         Executes nfdump on each nfcapd file. The nfdump program
                         can be specified in the config file using the prg key.
                         Generic arguments can be put with the key "args"

The default format is the format "print absolute". Note the format must be enclosed by
quotation marks.


"""
        sys.exit(exitcode)

    def get_databases_list(self):
        dbdir  = self.config.get('indexer','dbdir')
        files = []
        for dirname, dirnames, filenames in os.walk(dbdir):
            for filename in filenames:
                files.append(os.path.join(dirname, filename))
        return files


    def open_databases(self):
        self.dbobjs = []
        for i in self.get_databases_list():
            db = DB()
            if not db.open(i, DB.OREADER ):
                print >>sys.stderr, "open error: " + str(db.error())
                sys.exit(1)
            self.dbobjs.append(db)

    def probe_file(self,fn):
        for f in self.flowdirs:
            g = f + os.sep + fn
            if os.path.exists(g):
                return g
        return None

    def get_filename(self, db, idx):
        k = "d:"+str(idx)
        return db.get(k)



    def print_filenames(self):
        dbdir = self.config.get('indexer','dbdir')
        self.open_databases()
        ky = self.kco.build_key(self.ipaddress)
        for db in self.dbobjs:
            y=db.get(ky)
            if y != None:
                indexes =  self.kco.parse_index_value(y)
                for i in indexes:
                    fn=self.get_filename(db,i)
                    afn  = self.probe_file(fn)
                    print self.ipaddress, afn


    def print_rel_filenames(self):
        dbdir = self.config.get('indexer','dbdir')
        self.open_databases()
        ky = self.kco.build_key(self.ipaddress)
        for db in self.dbobjs:
            y=db.get(ky)
            if y != None:
                indexes =  self.kco.parse_index_value(y)
                for i in indexes:
                    fn=self.get_filename(db,i)
                    print self.ipaddress, fn


    def getfull_flows(self):
        try:
            prg = self.config.get("nfdump","prg")
            args = self.config.get("nfdump", "args")
            dbdir = self.config.get('indexer','dbdir')
        except ConfigParser.NoSectionError,e:
            sys.stderr.write(str(e)+ "\n")
            sys.exit(1)
        self.open_databases()

        ky = self.kco.build_key(self.ipaddress)
        for db in self.dbobjs:
            y=db.get(ky)
            if y != None:
                indexes =  self.kco.parse_index_value(y)
                for i in indexes:
                    fn=self.get_filename(db,i)
                    afn  = self.probe_file(fn)
                    cmd = prg + " " + args +" -r " + afn  + " \"ip "+self.ipaddress + "\""
                    print "#"+ cmd
                    r = os.system(cmd)
                    if r != 0:
                        self.kco.dbg("nfdump failed exitcode = "+  str(r) + "\n")
                        sys.exit(1)


    #Returns False if the ipaddress is not found
    #Returns True if the ipaddress is found
    def check_address(self):
        dbdir = self.config.get('indexer', 'dbdir')
        self.open_databases()
        ky = self.kco.build_key(self.ipaddress)
        for db in self.dbobjs:
            y = db.get(ky)
            if y == None:
                return False
            else:
                return True

def main_function():
    #### main function

    ipaddress=None
    format=None
    kl = Klookup()

    try:
        #Parse command line arguments
        opts, args = getopt.getopt(sys.argv[1:],'hf:i:c:')
        for o,a in opts:
            if o == '-h':
                kl.usage(0)
            elif o == '-i':
                ipaddress = a
            elif o == '-c':
                kl.configFile = a
            elif o =='-f':
                format = a
        if ipaddress == None:
            sys.stderr.write('An IP address or a list of IP addresses must be specified\n')
            sys.exit(1)

        kl.load()
        kl.ipaddress = ipaddress

        if (format != None):
            if format.startswith('check'):
                if kl.check_address():
                    sys.exit(0)
                else:
                    sys.exit(1)

            if format.startswith('print relative'):
                kl.print_rel_filenames();
                sys.exit(0)

            if format.startswith('print full'):
                kl.getfull_flows()
                sys.exit(0)

        #Here some printing is done
        print "#Database directory ", kl.config.get('indexer', 'dbdir')
        print "#IP address ", ipaddress
        print "#Configfile", kl.configFile

        #default format
        startdate=time.time()
        kl.print_filenames()
    except getopt.GetoptError,e:
        sys.stderr.write(str(e)+ '\n')
        sys.exit(1)
    endtime=time.time()
    d = endtime-startdate
    print "#Processing time: ",d
    sys.exit(0)

if __name__ == '__main__':
    main_function()
