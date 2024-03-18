#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024 David Straub
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
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#

"""Unit tests for the Undo History addon."""

import os
import shutil
import tempfile
import time
import unittest

from gramps.gen.db import DbTxn, DbWriteBase
from gramps.gen.db.dbconst import DBBACKEND
from gramps.gen.db.utils import make_database
from gramps.gen.lib import (
    Citation,
    Event,
    Family,
    Media,
    Note,
    Person,
    Place,
    Repository,
    Source,
    Tag,
)

DBID = "sqlite+history"


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class TestUndoHistory(unittest.TestCase):
    """Tests Undo History Addon."""

    @classmethod
    def setUpClass(cls) -> None:
        pass

    def setUp(self) -> None:
        self.dbdir = tempfile.mkdtemp()
        self.db: DbWriteBase = make_database(DBID)
        backend_path = os.path.join(self.dbdir, DBBACKEND)
        with open(backend_path, "w") as backend_file:
            backend_file.write(DBID)
        self.db.load(self.dbdir)

        with DbTxn("Add test objects", self.db) as trans:
            for i in range(10):
                self.__add_object(Person, self.db.add_person, trans)
                self.__add_object(Family, self.db.add_family, trans)
                self.__add_object(Event, self.db.add_event, trans)
                self.__add_object(Place, self.db.add_place, trans)
                self.__add_object(Repository, self.db.add_repository, trans)
                self.__add_object(Source, self.db.add_source, trans)
                self.__add_object(Citation, self.db.add_citation, trans)
                self.__add_object(Media, self.db.add_media, trans)
                self.__add_object(Note, self.db.add_note, trans)
                self.__add_object(Tag, self.db.add_tag, trans)

    @classmethod
    def tearDownClass(cls):
        pass

    def tearDown(self):
        shutil.rmtree(self.dbdir)

    def __add_object(self, obj_class, add_func, trans):
        """Add an object."""
        obj = obj_class()
        add_func(obj, trans)

    def _get_history_table(self, table_name):
        """Get a table from the history database."""
        dbundo = self.db.get_undodb()
        with dbundo._connect() as connection:
            connection.row_factory = dict_factory
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {table_name}")
            return cursor.fetchall()

    def test_initial_sate(self):
        assert self.db.get_number_of_people() == 10
        sessions = self._get_history_table("sessions")
        assert len(sessions) == 1
        assert sessions[0]["id"] == 1
        assert time.time() - sessions[0]["timestamp"] / 1e9 < 10
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 1
        assert transactions[0]["session"] == 1
        assert transactions[0]["id"] == 1
        assert transactions[0]["description"] == "Add test objects"
        assert transactions[0]["timestamp"] - sessions[0]["timestamp"] < 10e9
        assert transactions[0]["undo"] == 0
        commits = self._get_history_table("commits")
        assert len(commits) == 100
        for commit in commits:
            assert commit["session"] == 1
            assert commit["trans_type"] == 0  # add
            assert commit["timestamp"] < transactions[0]["timestamp"]
        assert len([com for com in commits if com["obj_class"] == "Person"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Family"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Event"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Place"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Repository"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Source"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Citation"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Media"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Note"]) == 10
        assert len([com for com in commits if com["obj_class"] == "Tag"]) == 10

    def test_undo_redo_initial_state(self):
        assert self.db.get_number_of_people() == 10
        self.db.undo()
        sessions = self._get_history_table("sessions")
        assert len(sessions) == 1
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 2
        assert transactions[1]["description"] == "_Undo Add test objects"
        commits = self._get_history_table("commits")
        assert len(commits) == 100
        assert self.db.get_number_of_people() == 0
        self.db.redo()
        transactions = self._get_history_table("transactions")
        assert len(transactions) == 3
        assert transactions[1]["description"] == "_Undo Add test objects"
        assert transactions[2]["description"] == "_Redo Add test objects"
        commits = self._get_history_table("commits")
        assert len(commits) == 100
        assert self.db.get_number_of_people() == 10
