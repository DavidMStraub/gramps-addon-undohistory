#
# Gramps - a GTK+/GNOME based genealogy program
#
# Copyright (C) 2024 David Straub <straub@protonmail.com>
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
register(
    DATABASE,
    id="sqlite+history",
    name=_("SQLite with Undo History"),
    name_accell=_("SQLite Database with Undo _History"),
    description=_("SQLite Database with Undo History"),
    version="0.1.0",
    gramps_target_version="5.2",
    status=STABLE,
    fname="undohistory.py",
    databaseclass="DbUndoSQLite",
    authors=["David Straub"],
    authors_email=["straub@protonmail.com"],
    # requires_mod=["SQLAlchemy"],
)
