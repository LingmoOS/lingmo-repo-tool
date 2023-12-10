#! /usr/bin/env python3

"""
Display information about files related to a specific source package/version
Display information about package(s) (suite, version, etc.)

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2000, 2001, 2002, 2003, 2004, 2005, 2006  James Troup <james@nocrew.org>
@license: GNU General Public License version 2 or later

"""
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

################################################################################

# < mhy> whilst you're here, if you have time to look at and merge
#        https://salsa.debian.org/ftp-team/dak/-/merge_requests/281 , I'd be
#        nice to you for at least 5 minutes
# < Ganneff> ...
# < Ganneff> 10!
# < mhy> Done
# ...
# < mhy> god I hate dak's argument parsing.  One day far in the future
#        when I have lots of time, I'm going to rip it all out
# < Ganneff> and replace it with rust
# * Ganneff hides
# < mhy> I'll replace *you* with rust
# < mhy> oh blast, I didn't even make 10 minutes

################################################################################

import sys
import apt_pkg

from pathlib import Path

from daklib.config import Config
from daklib.dbconn import DBConn, DBSource
from daklib import utils

################################################################################


def usage(exit_code=0):
    print("""Usage: dak find-files SOURCE_PACKAGE VERSION
Display file paths for files related to SOURCE_PACKAGE at VERSION
""")
    sys.exit(exit_code)

################################################################################


def main():
    cnf = Config()

    Arguments = [('h', "help", "FindFiles::Options::Help")]
    for i in ["help"]:
        key = "FindFiles::Options::%s" % i
        if key not in cnf:
            cnf[key] = ""

    package_details = apt_pkg.parse_commandline(cnf.Cnf, Arguments, sys.argv)
    Options = cnf.subtree("FindFiles::Options")

    if Options["Help"]:
        usage()

    if len(package_details) != 2:
        utils.fubar("require source package name and version")

    source, version = package_details

    session = DBConn().session()

    q = session.query(DBSource).filter_by(source=source, version=version)

    pkg = q.first()

    if pkg is None:
        utils.fubar(f"Source {source} at version {version} does not exist")

    filenames = []

    # Don't include pool otherwise we have to work out components (which may vary
    # by archive).  The partial path is enough for rsync to match it
    for binary in pkg.binaries:
        filenames.append(binary.poolfile.filename)

    for filename in sorted(filenames):
        print(filename)

######################################################################################


if __name__ == '__main__':
    main()
