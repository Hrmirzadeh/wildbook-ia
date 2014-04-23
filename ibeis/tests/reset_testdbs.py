#!/usr/bin/env python
# TODO: ADD COPYRIGHT TAG
from __future__ import absolute_import, division, print_function
import sys
import os
sys.path.append(os.getcwd())  # for windows
import ibeis
from ibeis.dev import main_commands
import utool
from os.path import join
from ibeis.injest import injest_testdata
from vtool.tests import grabdata

workdir = ibeis.params.get_workdir()


TESTDB0 = join(workdir, 'testdb0')
TESTDB1 = join(workdir, 'testdb1')
TESTDB_GUIALL = join(workdir, 'testdb_guiall')


def delete_testdbs():
    utool.delete(TESTDB0)
    utool.delete(TESTDB1)
    utool.delete(TESTDB_GUIALL)


def make_testdbs():
    from test_gui_import_images import TEST_GUI_IMPORT_IMAGES
    from test_gui_add_roi import TEST_GUI_ADD_ROI
    dbdir = TESTDB0
    main_locals = ibeis.main(dbdir=dbdir, gui=True)
    ibs = main_locals['ibs']
    back = main_locals['back']
    TEST_GUI_IMPORT_IMAGES(ibs, back)
    TEST_GUI_ADD_ROI(ibs, back)
    main_commands.set_default_dbdir(TESTDB0)


def reset_testdbs():
    grabdata.ensure_testdata()
    delete_testdbs()
    make_testdbs()
    injest_testdata.injest_testdata()


if __name__ == '__main__':
    reset_testdbs()
