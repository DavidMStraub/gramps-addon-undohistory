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

    def test_nothing(self):
        assert self.db.get_number_of_people() == 10
