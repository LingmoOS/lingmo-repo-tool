#!/usr/bin/env python
# vim:set et sw=4:

"""
Queue utility functions for dak

@contact: Debian FTP Master <ftpmaster@debian.org>
@copyright: 2001 - 2006 James Troup <james@nocrew.org>
@copyright: 2009, 2010  Joerg Jaspert <joerg@debian.org>
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

###############################################################################

from __future__ import absolute_import, print_function

import os
from . import utils
from types import *

from .dak_exceptions import *
from .regexes import *
from .config import Config
from .dbconn import *

################################################################################


def check_valid(overrides, session):
    """Check if section and priority for new overrides exist in database.

    Additionally does sanity checks:
      - debian-installer packages have to be udeb (or source)
      - non debian-installer packages cannot be udeb

    @type  overrides: list of dict
    @param overrides: list of overrides to check. The overrides need
                      to be given in form of a dict with the following keys:

                      - package: package name
                      - priority
                      - section
                      - component
                      - type: type of requested override ('dsc', 'deb' or 'udeb')

                      All values are strings.

    @rtype:  bool
    @return: C{True} if all overrides are valid, C{False} if there is any
             invalid override.
    """
    all_valid = True
    for o in overrides:
        o['valid'] = True
        if session.query(Priority).filter_by(priority=o['priority']).first() is None:
            o['valid'] = False
        if session.query(Section).filter_by(section=o['section']).first() is None:
            o['valid'] = False
        if get_mapped_component(o['component'], session) is None:
            o['valid'] = False
        if o['type'] not in ('dsc', 'deb', 'udeb'):
            raise Exception('Unknown override type {0}'.format(o['type']))
        if o['type'] == 'udeb' and o['section'] != 'debian-installer':
            o['valid'] = False
        if o['section'] == 'debian-installer' and o['type'] not in ('dsc', 'udeb'):
            o['valid'] = False
        all_valid = all_valid and o['valid']
    return all_valid

###############################################################################


def prod_maintainer(notes, upload):
    cnf = Config()
    changes = upload.changes
    whitelists = [upload.target_suite.mail_whitelist]

    # Here we prepare an editor and get them ready to prod...
    (fd, temp_filename) = utils.temp_filename()
    temp_file = os.fdopen(fd, 'w')
    temp_file.write("\n\n=====\n\n".join([note.comment for note in notes]))
    temp_file.close()
    editor = os.environ.get("EDITOR", "vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        temp_fh = open(temp_filename)
        prod_message = "".join(temp_fh.readlines())
        temp_fh.close()
        print("Prod message:")
        print(utils.prefix_multi_line_string(prod_message, "  ", include_blank_lines=1))
        prompt = "[P]rod, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
    os.unlink(temp_filename)
    if answer == 'A':
        return
    elif answer == 'Q':
        return 0
    # Otherwise, do the proding...
    user_email_address = utils.whoami() + " <%s>" % (
        cnf["Dinstall::MyAdminAddress"])

    changed_by = changes.changedby or changes.maintainer
    maintainer = changes.maintainer
    maintainer_to = utils.mail_addresses_for_upload(maintainer, changed_by, changes.fingerprint)

    Subst = {
        '__SOURCE__': upload.changes.source,
        '__CHANGES_FILENAME__': upload.changes.changesname,
        '__MAINTAINER_TO__': ", ".join(maintainer_to),
        }

    Subst["__FROM_ADDRESS__"] = user_email_address
    Subst["__PROD_MESSAGE__"] = prod_message
    Subst["__CC__"] = "Cc: " + cnf["Dinstall::MyEmailAddress"]

    prod_mail_message = utils.TemplateSubst(
        Subst, cnf["Dir::Templates"] + "/process-new.prod")

    # Send the prod mail
    utils.send_mail(prod_mail_message, whitelists=whitelists)

    print("Sent prodding message")

################################################################################


def edit_note(note, upload, session, trainee=False):
    # Write the current data to a temporary file
    (fd, temp_filename) = utils.temp_filename()
    editor = os.environ.get("EDITOR", "vi")
    answer = 'E'
    while answer == 'E':
        os.system("%s %s" % (editor, temp_filename))
        temp_file = open(temp_filename)
        newnote = temp_file.read().rstrip()
        temp_file.close()
        print("New Note:")
        print(utils.prefix_multi_line_string(newnote, "  "))
        prompt = "[D]one, Edit, Abandon, Quit ?"
        answer = "XXX"
        while prompt.find(answer) == -1:
            answer = utils.our_raw_input(prompt)
            m = re_default_answer.search(prompt)
            if answer == "":
                answer = m.group(1)
            answer = answer[:1].upper()
    os.unlink(temp_filename)
    if answer == 'A':
        return
    elif answer == 'Q':
        return 0

    comment = NewComment()
    comment.policy_queue = upload.policy_queue
    comment.package = upload.changes.source
    comment.version = upload.changes.version
    comment.comment = newnote
    comment.author = utils.whoami()
    comment.trainee = trainee
    session.add(comment)
    session.commit()

###############################################################################


def get_suite_version_by_source(source, session):
    'returns a list of tuples (suite_name, version) for source package'
    q = session.query(Suite.suite_name, DBSource.version). \
        join(Suite.sources).filter_by(source=source)
    return q.all()


def get_suite_version_by_package(package, arch_string, session):
    '''
    returns a list of tuples (suite_name, version) for binary package and
    arch_string
    '''
    return session.query(Suite.suite_name, DBBinary.version). \
        join(Suite.binaries).filter_by(package=package). \
        join(DBBinary.architecture). \
        filter(Architecture.arch_string.in_([arch_string, 'all'])).all()
