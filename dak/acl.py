#! /usr/bin/env python3
#
# Copyright (C) 2012, Ansgar Burchardt <ansgar@debian.org>
# Copyright (C) 2023 Emilio Pozuelo Monfort <pochu@debian.org>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import sys
from collections.abc import Iterable
from typing import NoReturn, Optional

from daklib.dbconn import DBConn, Fingerprint, Keyring, Suite, Uid, ACL


def usage(status: int = 0) -> NoReturn:
    print("""Usage:
  dak acl set-fingerprints <acl-name>
  dak acl export-per-source <acl-name>
  dak acl allow <acl-name> <fingerprint> <source>...
  dak acl deny <acl-name> <fingerprint> <source>...
  dak acl export-per-suite <acl-name>
  dak acl allow-suite <acl-name> <fingerprint> <suite>...
  dak acl deny-suite <acl-name> <fingerprint> <suite>...

  set-fingerprints:
    Reads list of fingerprints from stdin and sets the ACL <acl-name> to these.
    Accepted input formats are "uid:<uid>", "name:<name>" and
    "fpr:<fingerprint>".

  export-per-source:
    Export per source upload rights for ACL <acl-name>.

  allow, deny:
    Grant (revoke) per-source upload rights for ACL <acl-name>.

  export-per-suite:
    Export per suite upload rights for ACL <acl-name>.

  allow-suite, deny-suite:
    Grant (revoke) per-suite upload rights for ACL <acl-name>.
""")
    sys.exit(status)


def get_fingerprint(entry: str, session) -> Optional[Fingerprint]:
    """get fingerprint for given ACL entry

    The entry is a string in one of these formats::

        uid:<uid>
        name:<name>
        fpr:<fingerprint>
        keyring:<keyring-name>

    :param entry: ACL entry
    :param session: database session
    :return: fingerprint for the entry
    """
    field, value = entry.split(":", 1)
    q = session.query(Fingerprint).join(Fingerprint.keyring).filter(Keyring.active == True)  # noqa:E712

    if field == 'uid':
        q = q.join(Fingerprint.uid).filter(Uid.uid == value)
    elif field == 'name':
        q = q.join(Fingerprint.uid).filter(Uid.name == value)
    elif field == 'fpr':
        q = q.filter(Fingerprint.fingerprint == value)
    elif field == 'keyring':
        q = q.filter(Keyring.keyring_name == value)
    else:
        raise Exception('Unknown selector "{0}".'.format(field))

    return q.all()


def acl_set_fingerprints(acl_name: str, entries: Iterable[str]) -> None:
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    acl.fingerprints.clear()
    for entry in entries:
        entry = entry.strip()
        if entry.startswith('#') or len(entry) == 0:
            continue

        fps = get_fingerprint(entry, session)
        if len(fps) == 0:
            print("Unknown key for '{0}'".format(entry))
        else:
            acl.fingerprints.update(fps)

    session.commit()


def acl_export_per_source(acl_name: str) -> None:
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    query = r"""
      SELECT
        f.fingerprint,
        (SELECT COALESCE(u.name, '') || ' <' || u.uid || '>'
           FROM uid u
           JOIN fingerprint f2 ON u.id = f2.uid
          WHERE f2.id = f.id) AS name,
        STRING_AGG(
          a.source
          || COALESCE(' (' || (SELECT fingerprint FROM fingerprint WHERE id = a.created_by_id) || ')', ''),
          E',\n ' ORDER BY a.source)
      FROM acl_per_source a
      JOIN fingerprint f ON a.fingerprint_id = f.id
      LEFT JOIN uid u ON f.uid = u.id
      WHERE a.acl_id = :acl_id
      GROUP BY f.id, f.fingerprint
      ORDER BY name
      """

    for row in session.execute(query, {'acl_id': acl.id}):
        print("Fingerprint:", row[0])
        print("Uid:", row[1])
        print("Allow:", row[2])
        print()

    session.rollback()
    session.close()


def acl_export_per_suite(acl_name: str) -> None:
    session = DBConn().session()
    acl = session.query(ACL).filter_by(name=acl_name).one()

    query = r"""
      SELECT
        f.fingerprint,
        (SELECT COALESCE(u.name, '') || ' <' || u.uid || '>'
           FROM uid u
           JOIN fingerprint f2 ON u.id = f2.uid
          WHERE f2.id = f.id) AS name,
        s.suite_name
      FROM acl_per_suite a
      JOIN fingerprint f ON a.fingerprint_id = f.id
      JOIN suite s ON a.suite_id = s.id
      LEFT JOIN uid u ON f.uid = u.id
      WHERE a.acl_id = :acl_id
      GROUP BY f.id, f.fingerprint, s.suite_name
      ORDER BY name
      """

    for row in session.execute(query, {'acl_id': acl.id}):
        print("Fingerprint:", row[0])
        print("Uid:", row[1])
        print("Allow:", row[2])
        print()

    session.rollback()
    session.close()


def acl_allow(acl_name: str, fingerprint: str, sources: Iterable[str]) -> None:
    tbl = DBConn().tbl_acl_per_source

    session = DBConn().session()

    acl_id = session.query(ACL).filter_by(name=acl_name).one().id
    fingerprint_id = session.query(Fingerprint).filter_by(fingerprint=fingerprint).one().fingerprint_id

    # TODO: check that fpr is in ACL

    data = [
        {
            'acl_id': acl_id,
            'fingerprint_id': fingerprint_id,
            'source': source,
            'reason': 'set by {} via CLI'.format(os.environ.get('USER', '(unknown)')),
        }
        for source in sources
    ]

    session.execute(tbl.insert(), data)

    session.commit()


def acl_allow_suite(acl_name: str, fingerprint: str, suites: Iterable[str]) -> None:
    tbl = DBConn().tbl_acl_per_suite

    session = DBConn().session()

    acl_id = session.query(ACL).filter_by(name=acl_name).one().id
    fingerprint_id = session.query(Fingerprint).filter_by(fingerprint=fingerprint).one().fingerprint_id

    # TODO: check that fpr is in ACL

    data = []

    for suite in suites:
        try:
            suite_id = session.query(Suite).filter_by(suite_name=suite).one().suite_id
        except:
            suite_id = session.query(Suite).filter_by(codename=suite).one().suite_id

        data.append({
            'acl_id': acl_id,
            'fingerprint_id': fingerprint_id,
            'suite_id': suite_id,
            'reason': 'set by {} via CLI'.format(os.environ.get('USER', '(unknown)')),
        })

    session.execute(tbl.insert(), data)

    session.commit()


def acl_deny(acl_name: str, fingerprint: str, sources: Iterable[str]) -> None:
    tbl = DBConn().tbl_acl_per_source

    session = DBConn().session()

    acl_id = session.query(ACL).filter_by(name=acl_name).one().id
    fingerprint_id = session.query(Fingerprint).filter_by(fingerprint=fingerprint).one().fingerprint_id

    # TODO: check that fpr is in ACL

    for source in sources:
        result = session.execute(tbl.delete().where(tbl.c.acl_id == acl_id).where(tbl.c.fingerprint_id == fingerprint_id).where(tbl.c.source == source))
        if result.rowcount < 1:
            print("W: Tried to deny uploads of '{}', but was not allowed before.".format(source))

    session.commit()


def acl_deny_suite(acl_name: str, fingerprint: str, suites: Iterable[str]) -> None:
    tbl = DBConn().tbl_acl_per_suite

    session = DBConn().session()

    acl_id = session.query(ACL).filter_by(name=acl_name).one().id
    fingerprint_id = session.query(Fingerprint).filter_by(fingerprint=fingerprint).one().fingerprint_id

    # TODO: check that fpr is in ACL

    for suite in suites:
        try:
            suite_id = session.query(Suite).filter_by(suite_name=suite).one().suite_id
        except:
            suite_id = session.query(Suite).filter_by(codename=suite).one().suite_id

        result = session.execute(tbl.delete().where(tbl.c.acl_id == acl_id).where(tbl.c.fingerprint_id == fingerprint_id).where(tbl.c.suite_id == suite_id))
        if result.rowcount < 1:
            print("W: Tried to deny uploads for suite '{}', but was not allowed before.".format(suite))

    session.commit()


def main(argv=None):
    if argv is None:
        argv = sys.argv

    if len(argv) > 1 and argv[1] in ('-h', '--help'):
        usage(0)

    if len(argv) < 3:
        usage(1)

    if argv[1] == 'set-fingerprints':
        acl_set_fingerprints(argv[2], sys.stdin)
    elif argv[1] == 'export-per-source':
        acl_export_per_source(argv[2])
    elif argv[1] == 'export-per-suite':
        acl_export_per_suite(argv[2])
    elif argv[1] == 'allow':
        acl_allow(argv[2], argv[3], argv[4:])
    elif argv[1] == 'deny':
        acl_deny(argv[2], argv[3], argv[4:])
    elif argv[1] == 'allow-suite':
        acl_allow_suite(argv[2], argv[3], argv[4:])
    elif argv[1] == 'deny-suite':
        acl_deny_suite(argv[2], argv[3], argv[4:])
    else:
        usage(1)
