#!/usr/bin/env python
# -*- encoding: utf-8 -*-

from __future__ import print_function

import sip
sip.setapi('QString', 2)
#API_NAMES = ["QDate", "QDateTime", "QString", "QTextStream", "QTime", "QUrl", "QVariant"]
#API_VERSION = 2
#for name in API_NAMES:
    #sip.setapi(name, API_VERSION)

from PyQt4 import QtCore
from PyQt4 import QtGui

from PyQt4.QtCore import Qt, QRect, QEvent, SIGNAL, \
    QAbstractTableModel, QModelIndex, QVariant, QMimeData

from PyQt4.QtGui import QApplication, QMainWindow, QWidget, QFrame, \
    QMenuBar, QMenu, QAction, QActionGroup, QToolBar, QClipboard, \
    QTabWidget, QSplitter, QVBoxLayout, QHBoxLayout, \
    QTableView, QAbstractItemView, QItemDelegate, \
    QListWidget, QListWidgetItem, QComboBox, \
    QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, \
    QTextEdit, QTextDocument, QLineEdit, QTextCursor, QTextCharFormat, QTextOption, \
    QButtonGroup, QRadioButton, QPushButton, QToolButton, QCheckBox, QKeySequence, \
    QStyleOption, QStyle, QIcon, QLabel, QPixmap, \
    QDialog, QFileDialog, QInputDialog, QMessageBox, \
    QFontDialog, QFontDatabase, QFont, QFontMetrics, \
    QColorDialog, QColor, QKeyEvent

from qutepart import Qutepart
from qutepart.completer import Completer

import os, sys

_DEFAULT_COMPLETION_THRESHOLD = 3
_DEFAULT_COMPLETION_ENABLED = True

def main():  
    app = QApplication(sys.argv)
    
    window = QMainWindow()
    
    wrdlst = ['SELECT', 'FROM', 'abc_db', 'def_db']
    parchidict = {'abc_db': ['ghi_tbl', 'jkl_tbl'],
                  'def_db': ['mno_tbl', 'pqr_tbl'],
                  'ghi_tbl': ['stu_col', 'vwx_col'],
                  'jkl_tbl': ['yza_col', 'bcd_col']}

    qpart = Qutepart(ContentAutoComplete=False,
                     WordList=wrdlst, ParentChildDict=parchidict)
    window.setCentralWidget(qpart)

    fnt = QFont()
    fnt.setFamily('Lucida Sans Unicode')
    if (True): fnt.setPointSize(18) # Current_OS == Mac_OS
    else: fnt.setPointSize(11)
    qpart.setFont(fnt)

    qpart.detectSyntax(language='SQL (MySQL)') # (sourceFilePath=text_file_path, firstLine=firstLine)
    qpart.lineLengthEdge = 80
    
    qpart.indentUseTabs = False
    
    qpart.setWordWrapMode(QTextOption.NoWrap)
    
    qpart.setWindowTitle('Test SQL Enhancements')
    
    menu = {'Bookmarks': ('toggleBookmarkAction',
                          'nextBookmarkAction',
                          'prevBookmarkAction'),
            'Navigation':('scrollUpAction',
                          'scrollDownAction',
                          'selectAndScrollUpAction',
                          'selectAndScrollDownAction',
                          ),
            'Edit'      : ('decreaseIndentAction',
                           'autoIndentLineAction',
                           'moveLineUpAction',
                           'moveLineDownAction',
                           'deleteLineAction',
                           'copyLineAction',
                           'pasteLineAction',
                           'cutLineAction',
                           'duplicateLineAction',
                           'invokeCompletionAction',
                           )
    }
    for k, v in menu.items():
        menuObject = window.menuBar().addMenu(k)
        for actionName in v:
            menuObject.addAction(getattr(qpart, actionName))
    
    window.resize(800, 600)
    window.show()
 
    return app.exec_()

if __name__ == '__main__':
    main()
 
