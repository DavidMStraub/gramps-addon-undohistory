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

"""SQLite database with undo history."""

import pickle
from contextlib import contextmanager
from time import time_ns
from typing import List, Optional

from gramps.gen.const import GRAMPS_LOCALE as glocale
from gramps.gen.db import REFERENCE_KEY, TXNADD, TXNDEL, TXNUPD, DbUndo, DbWriteBase
from gramps.gen.db.dbconst import CLASS_TO_KEY_MAP, KEY_TO_CLASS_MAP, KEY_TO_NAME_MAP
from gramps.gen.db.txn import DbTxn
from gramps.plugins.db.dbapi.sqlite import SQLite
from sqlalchemy import BLOB, Column, Integer, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

_ = glocale.translation.gettext

Base = declarative_base()


class Undo(Base):
    __tablename__ = "commits"

    session = Column(Integer, primary_key=True)
    id = Column(Integer, primary_key=True)
    obj_class = Column(Text)
    trans_type = Column(Integer)
    obj_handle = Column(Text)
    ref_handle = Column(Text)
    old_data = Column(BLOB)
    new_data = Column(BLOB)
    json = Column(Text)
    timestamp = Column(Integer)


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    timestamp = Column(Integer)
    treeid = Column(Integer)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    session = Column(Integer)
    description = Column(Text)
    timestamp = Column(Integer)
    first = Column(Integer)
    last = Column(Integer)
    undo = Column(Integer)


class DbUndoSQLite(SQLite):
    """SQLite database backend with undo history."""

    def _create_undo_manager(self) -> DbUndo:
        """Create the undo manager."""
        path = self.undolog
        return DbUndoSQL(grampsdb=self, dburl=f"sqlite:///{path}")


class DbUndoSQL(DbUndo):
    """SQL-based undo database."""

    def __init__(
        self, grampsdb: DbWriteBase, dburl: str, treeid: Optional[int] = None
    ) -> None:
        DbUndo.__init__(self, grampsdb)
        self._session_id: Optional[int] = None
        self.treeid = None
        self.undodb: List[bytes] = []
        self.engine = create_engine(dburl)

    @contextmanager
    def session_scope(self):
        """Provide a transactional scope around a series of operations."""
        SQLSession = sessionmaker(self.engine)
        session = SQLSession()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()

    @property
    def session_id(self) -> int:
        """Return the cached session ID or create if not exists."""
        if self._session_id is None:
            self._session_id = self._make_session_id()
        return self._session_id

    def open(self, value=None) -> None:
        """
        Open the backing storage.
        """
        Base.metadata.create_all(self.engine)

    def _make_session_id(self) -> int:
        """Insert a row into the session table."""
        with self.session_scope() as session:
            new_session = Session(timestamp=time_ns(), treeid=self.treeid)
            session.add(new_session)
            session.commit()
            return new_session.id

    def close(self) -> None:
        """Close the backing storage."""
        pass

    def append(self, value) -> None:
        """Add a new entry on the end."""
        (obj_type, trans_type, handle, old_data, new_data) = pickle.loads(value)
        if isinstance(handle, tuple):
            obj_handle, ref_handle = handle
        else:
            obj_handle, ref_handle = (handle, None)
        length = len(self)
        session_id = self.session_id  # outside session to prevent lock error
        with self.session_scope() as session:
            old_data = None if old_data is None else pickle.dumps(old_data, protocol=1)
            new_data = None if new_data is None else pickle.dumps(new_data, protocol=1)
            new_undo = Undo(
                session=session_id,
                id=length + 1,
                obj_class=KEY_TO_CLASS_MAP.get(obj_type, str(obj_type)),
                trans_type=trans_type,
                obj_handle=obj_handle,
                ref_handle=ref_handle,
                old_data=old_data,
                new_data=new_data,
                timestamp=time_ns(),
            )
            session.add(new_undo)
            session.commit()

    def _after_commit(
        self, transaction: DbTxn, undo: bool = False, redo: bool = False
    ) -> None:
        """Post-transaction commit processing."""
        msg = transaction.get_description()
        if redo:
            msg = _("_Redo %s") % msg
        if undo:
            msg = _("_Undo %s") % msg
        if undo or redo:
            timestamp = time_ns()  # update timestamp to now
        else:
            timestamp = int(transaction.timestamp * 1e9)  # integer nanoseconds
        if transaction.first is None:
            first = None
        else:
            first = transaction.first + 1  # Python index vs SQL id off-by-1
        if transaction.last is None:
            last = None
        else:
            last = transaction.last + 1
        session_id = self.session_id  # outside session to prevent lock error
        with self.session_scope() as session:
            new_transaction = Transaction(
                session=session_id,
                description=msg,
                timestamp=timestamp,
                first=first,
                last=last,
                undo=int(undo),
            )
        session.add(new_transaction)
        session.commit()

    def __getitem__(self, index: int) -> bytes:
        """
        Returns an entry by index number.
        """
        session_id = self.session_id  # outside session to prevent lock error
        with self.session_scope() as session:
            undo_record = (
                session.query(Undo)
                .filter(Undo.session == session_id, Undo.id == index + 1)
                .first()
            )

            if undo_record is None:
                raise IndexError("list index out of range")

            obj_class = int(
                CLASS_TO_KEY_MAP.get(undo_record.obj_class, undo_record.obj_class)
            )
            old_data = (
                None
                if undo_record.old_data is None
                else pickle.loads(undo_record.old_data)
            )
            new_data = (
                None
                if undo_record.new_data is None
                else pickle.loads(undo_record.new_data)
            )

            if undo_record.ref_handle:
                handle = (undo_record.obj_handle, undo_record.ref_handle)
            else:
                handle = undo_record.obj_handle

            blob_data = pickle.dumps(
                (obj_class, undo_record.trans_type, handle, old_data, new_data),
                protocol=1,
            )
            return blob_data

    def __setitem__(self, index: int, value: bytes) -> None:
        """
        Set an entry to a value.
        """
        (obj_type, trans_type, handle, old_data, new_data) = pickle.loads(value)
        if isinstance(handle, tuple):
            obj_handle, ref_handle = handle
        else:
            obj_handle, ref_handle = (handle, None)
        session_id = self.session_id  # outside session to prevent lock error
        with self.session_scope() as session:
            undo_record = (
                session.query(Undo)
                .filter(Undo.session == session_id, Undo.id == index + 1)
                .first()
            )

            if undo_record is None:
                raise IndexError("list index out of range")

            undo_record.obj_class = KEY_TO_CLASS_MAP.get(obj_type, str(obj_type))
            undo_record.trans_type = trans_type
            undo_record.obj_handle = obj_handle
            undo_record.ref_handle = ref_handle
            undo_record.old_data = (
                pickle.dumps(old_data, protocol=1) if old_data is not None else None
            )
            undo_record.new_data = (
                pickle.dumps(new_data, protocol=1) if new_data is not None else None
            )
            undo_record.timestamp = time_ns()

            session.commit()

    def __len__(self) -> int:
        """Returns the number of entries."""
        session_id = self.session_id  # outside session to prevent lock error
        with self.session_scope() as session:
            max_id = (
                session.query(func.max(Undo.id))
                .filter(Undo.session == session_id)
                .scalar()
            )
        return max_id or 0

    def _redo(self, update_history: bool) -> bool:
        """
        Access the last undone transaction, and revert the data to the state
        before the transaction was undone.
        """
        txn = self.redoq.pop()
        self.undoq.append(txn)
        transaction = txn
        db = self.db
        subitems = transaction.get_recnos()
        # sigs[obj_type][trans_type]
        sigs = [[[] for trans_type in range(3)] for key in range(11)]
        records = {record_id: self[record_id] for record_id in subitems}

        # Process all records in the transaction
        try:
            self.db._txn_begin()
            for record_id in subitems:
                (key, trans_type, handle, old_data, new_data) = pickle.loads(
                    records[record_id]
                )

                if key == REFERENCE_KEY:
                    self.db.undo_reference(new_data, handle)
                else:
                    self.db.undo_data(new_data, handle, key)
                    sigs[key][trans_type].append(handle)
            # now emit the signals
            self.undo_sigs(sigs, False)

            self.db._txn_commit()
        except:
            self.db._txn_abort()
            raise

        # Notify listeners
        if db.undo_callback:
            db.undo_callback(_("_Undo %s") % transaction.get_description())

        if db.redo_callback:
            if self.redo_count > 1:
                new_transaction = self.redoq[-2]
                db.redo_callback(_("_Redo %s") % new_transaction.get_description())
            else:
                db.redo_callback(None)

        if update_history and db.undo_history_callback:
            db.undo_history_callback()

        self._after_commit(transaction, undo=False, redo=True)

        return True

    def _undo(self, update_history: bool) -> bool:
        """
        Access the last committed transaction, and revert the data to the
        state before the transaction was committed.
        """
        txn = self.undoq.pop()
        self.redoq.append(txn)
        transaction = txn
        db = self.db
        subitems = transaction.get_recnos(reverse=True)
        # sigs[obj_type][trans_type]
        sigs = [[[] for trans_type in range(3)] for key in range(11)]
        records = {record_id: self[record_id] for record_id in subitems}

        # Process all records in the transaction
        try:
            self.db._txn_begin()
            for record_id in subitems:
                (key, trans_type, handle, old_data, new_data) = pickle.loads(
                    records[record_id]
                )

                if key == REFERENCE_KEY:
                    self.db.undo_reference(old_data, handle)
                else:
                    self.db.undo_data(old_data, handle, key)
                    sigs[key][trans_type].append(handle)
            # now emit the signals
            self.undo_sigs(sigs, True)

            self.db._txn_commit()
        except:
            self.db._txn_abort()
            raise

        # Notify listeners
        if db.undo_callback:
            if self.undo_count > 0:
                db.undo_callback(_("_Undo %s") % self.undoq[-1].get_description())
            else:
                db.undo_callback(None)

        if db.redo_callback:
            db.redo_callback(_("_Redo %s") % transaction.get_description())

        if update_history and db.undo_history_callback:
            db.undo_history_callback()

        self._after_commit(transaction, undo=True, redo=False)

        return True

    def undo_sigs(self, sigs, undo):
        """
        Helper method to undo/redo the signals for changes made
        We want to do deletes and adds first
        Note that if 'undo' we swap emits
        """
        for trans_type in [TXNDEL, TXNADD, TXNUPD]:
            for obj_type in range(11):
                handles = sigs[obj_type][trans_type]
                if handles:
                    if (
                        not undo
                        and trans_type == TXNDEL
                        or undo
                        and trans_type == TXNADD
                    ):
                        typ = "-delete"
                    else:
                        # don't update a handle if its been deleted, and note
                        # that 'deleted' handles are in the 'add' list if we
                        # are undoing
                        handles = [
                            handle
                            for handle in handles
                            if handle not in sigs[obj_type][TXNADD if undo else TXNDEL]
                        ]
                        if ((not undo) and trans_type == TXNADD) or (
                            undo and trans_type == TXNDEL
                        ):
                            typ = "-add"
                        else:  # TXNUPD
                            typ = "-update"
                    if handles:
                        self.db.emit(KEY_TO_NAME_MAP[obj_type] + typ, (handles,))


class Cursor:
    def __init__(self, iterator):
        self.iterator = iterator
        self._iter = self.__iter__()

    def __enter__(self):
        return self

    def __iter__(self):
        for handle, data in self.iterator():
            yield (handle, data)

    def __next__(self):
        try:
            return self._iter.__next__()
        except StopIteration:
            return None

    def __exit__(self, *args, **kwargs):
        pass

    def iter(self):
        for handle, data in self.iterator():
            yield (handle, data)

    def first(self):
        self._iter = self.__iter__()
        try:
            return next(self._iter)
        except:
            return

    def next(self):
        try:
            return next(self._iter)
        except:
            return

    def close(self):
        pass
