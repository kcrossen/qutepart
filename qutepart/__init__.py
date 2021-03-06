"""qutepart --- Code editor component for PyQt and Pyside
=========================================================
"""

import os.path
import logging
import platform

from PyQt4.QtCore import QRect, Qt, pyqtSignal
from PyQt4.QtGui import QAction, QApplication, QColor, QBrush, QDialog, QFont, \
                        QIcon, QKeyEvent, QKeySequence, QPainter, QPen, QPalette, \
                        QPlainTextEdit, \
                        QPrintDialog, QShortcut, QTextCharFormat, QTextCursor, \
                        QTextBlock, QTextEdit, QTextFormat

from qutepart.syntax import SyntaxManager
from qutepart.syntaxhlighter import SyntaxHighlighter
from qutepart.brackethlighter import BracketHighlighter
from qutepart.completer import Completer
from qutepart.lines import Lines
from qutepart.rectangularselection import RectangularSelection
import qutepart.sideareas
from qutepart.indenter import Indenter
import qutepart.bookmarks


VERSION = (1, 3, 0)


logger = logging.getLogger('qutepart')
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logging.Formatter("qutepart: %(message)s"))
logger.addHandler(consoleHandler)

logger.setLevel(logging.ERROR)


# After logging setup
import qutepart.syntax.loader
binaryParserAvailable = qutepart.syntax.loader.binaryParserAvailable


_ICONS_PATH = os.path.join(os.path.dirname(__file__), 'icons')

def getIconPath(iconFileName):
    return os.path.join(_ICONS_PATH, iconFileName)


#Define for old Qt versions methods, which appeared in 4.7
if not hasattr(QTextCursor, 'positionInBlock'):
    def _positionInBlock(cursor):
        return cursor.position() - cursor.block().position()
    QTextCursor.positionInBlock = _positionInBlock

if not hasattr(QTextCursor, 'setPositionInBlock'):
    if not hasattr(QTextCursor, 'MoveAnchor'):  # using a mock, avoiding crash. See doc/source/conf.py
        QTextCursor.MoveAnchor = None
    def _setPositionInBlock(cursor, positionInBlock, anchor=QTextCursor.MoveAnchor):
        return cursor.setPosition(cursor.block().position() + positionInBlock, anchor)
    QTextCursor.setPositionInBlock = _setPositionInBlock


class Qutepart(QPlainTextEdit):
    '''Qutepart is based on QPlainTextEdit, and you can use QPlainTextEdit methods,
    if you don't see some functionality here.

    **Text**

    ``text`` attribute holds current text. It may be read and written.::

        qpart.text = readFile()
        saveFile(qpart.text)

    This attribute always returns text, separated with ``\\n``. Use ``textForSaving()`` for get original text.

    It is recommended to use ``lines`` attribute whenever possible,
    because access to ``text`` might require long time on big files.
    Attribute is cached, only first read access after text has been changed in slow.

    **Selected text**

    ``selectedText`` attribute holds selected text. It may be read and written.
    Write operation replaces selection with new text. If nothing is selected - just inserts text::

        print qpart.selectedText  # print selection
        qpart.selectedText = 'new text'  # replace selection

    **Text lines**

    ``lines`` attribute, which represents text as list-of-strings like object
    and allows to modify it. Examples::

        qpart.lines[0]  # get the first line of the text
        qpart.lines[-1]  # get the last line of the text
        qpart.lines[2] = 'new text'  # replace 3rd line value with 'new text'
        qpart.lines[1:4]  # get 3 lines of text starting from the second line as list of strings
        qpart.lines[1:4] = ['new line 2', 'new line3', 'new line 4']  # replace value of 3 lines
        del qpart.lines[3]  # delete 4th line
        del qpart.lines[3:5]  # delete lines 4, 5, 6

        len(qpart.lines)  # get line count

        qpart.lines.append('new line')  # append new line to the end
        qpart.lines.insert(1, 'new line')  # insert new line before line 1

        print qpart.lines  # print all text as list of strings

        # iterate over lines.
        for lineText in qpart.lines:
            doSomething(lineText)

        qpart.lines = ['one', 'thow', 'three']  # replace whole text

    **Position and selection**

    * ``cursorPosition`` - cursor position as ``(line, column)``. Lines are numerated from zero. If column is set to ``None`` - cursor will be placed before first non-whitespace character. If line or column is bigger, than actual file, cursor will be placed to the last line, to the last column
    * ``absCursorPosition`` - cursor position as offset from the beginning of text.
    * ``selectedPosition`` - selection coordinates as ``((startLine, startCol), (cursorLine, cursorCol))``.
    * ``absSelectedPosition`` - selection coordinates as ``(startPosition, cursorPosition)`` where position is offset from the beginning of text.
    Rectangular selection is not available via API currently.

    **EOL, indentation, edge**

    * ``eol`` - End Of Line character. Supported values are ``\\n``, ``\\r``, ``\\r\\n``. See comments for ``textForSaving()``
    * ``indentWidth`` - Width of ``Tab`` character, and width of one indentation level. Default is ``4``.
    * ``indentUseTabs`` - If True, ``Tab`` character inserts ``\\t``, otherwise - spaces. Default is ``False``.
    * ``lineLengthEdge`` - If not ``None`` - maximal allowed line width (i.e. 80 chars). Longer lines are marked with red (see ``lineLengthEdgeColor``) line. Default is ``None``.
    * ``lineLengthEdgeColor`` - Color of line length edge line. Default is red.

    **Visible white spaces**

    * ``drawWhiteSpaceTrailing`` - Draw trailing whitespaces. Default is ``True``.
    * ``drawWhiteSpaceAnyIndentation`` - Draw trailing and other whitespaces, used as indentation. Default is ``False``.

    **Autocompletion**

    Qutepart supports autocompletion, based on document contents.
    It is enabled, if ``completionEnabled`` is ``True``.
    ``completionThreshold`` is count of typed symbols, after which completion is shown.

    **Actions**

    Component contains list of actions (QAction instances).
    Actions can be insered to some menu, a shortcut and an icon can be configured.

    Bookmarks:

    * ``toggleBookmarkAction`` - Set/Clear bookmark on current block
    * ``nextBookmarkAction`` - Jump to next bookmark
    * ``prevBookmarkAction`` - Jump to previous bookmark

    Scroll:

    * ``scrollUpAction`` - Scroll viewport Up
    * ``scrollDownAction`` - Scroll viewport Down
    * ``selectAndScrollUpAction`` - Select 1 line Up and scroll
    * ``selectAndScrollDownAction`` - Select 1 line Down and scroll

    Indentation:

    * ``decreaseIndentAction`` - Decrease indentation
    * ``autoIndentLineAction`` - Autoindent line
    * ``indentWithSpaceAction`` - Indent all selected lines by 1 space symbol
    * ``unIndentWithSpaceAction`` - Unindent all selected lines by 1 space symbol

    Lines:

    * ``moveLineUpAction`` - Move line Up
    * ``moveLineDownAction`` - Move line Down
    * ``deleteLineAction`` - Delete line
    * ``copyLineAction`` - Copy line
    * ``pasteLineAction`` - Paste line
    * ``cutLineAction`` - Cut line
    * ``duplicateLineAction`` - Duplicate line

    Other:

    * ``invokeCompletionAction`` - Invoke completion
    * ``printAction`` - Print file

    **Text modification and Undo/Redo**

    Sometimes, it is required to make few text modifications, which are Undo-Redoble as atomic operation.
    i.e. you want to indent (insert indentation) few lines of text, but user shall be able to
    Undo it in one step. In this case, you can use Qutepart as a context manager.::

        with qpart:
            qpart.modifySomeText()
            qpart.modifyOtherText()

    Nested atomic operations are joined in one operation

    **Signals**

    * ``userWarning(text)``` Warning, which shall be shown to the user on status bar. I.e. 'Rectangular selection area is too big'
    * ``languageChanged(langName)``` Language has changed. See also ``language()``
    * ``indentWidthChanged(int)`` Indentation width changed. See also ``indentWidth``
    * ``indentUseTabsChanged(bool)`` Indentation uses tab property changed. See also ``indentUseTabs``
    * ``eolChanged(eol)`` EOL mode changed. See also ``eol``.

    **Public methods**
    '''

    userWarning = pyqtSignal(unicode)
    languageChanged = pyqtSignal(unicode)
    indentWidthChanged = pyqtSignal(int)
    indentUseTabsChanged = pyqtSignal(bool)
    eolChanged = pyqtSignal(unicode)

    _DEFAULT_EOL = '\n'

    _DEFAULT_COMPLETION_THRESHOLD = 3
    _DEFAULT_COMPLETION_ENABLED = True

    _globalSyntaxManager = SyntaxManager()

    def __init__(self, *args):
        QPlainTextEdit.__init__(self, *args)

        # toPlainText() takes a lot of time on long texts, therefore it is cached
        self._cachedText = None

        self._eol = self._DEFAULT_EOL
        self._indenter = Indenter(self)
        self.lineLengthEdge = None
        self.lineLengthEdgeColor = Qt.red
        self._atomicModificationDepth = 0

        self.drawWhiteSpaceTrailing = True
        self.drawWhiteSpaceAnyIndentation = False

        self._rectangularSelection = RectangularSelection(self)

        """Sometimes color themes will be supported.
        Now black on white is hardcoded in the highlighters.
        Hardcode same palette for not highlighted text
        """
        palette = self.palette()
        palette.setColor(QPalette.Base, QColor('#ffffff'))
        palette.setColor(QPalette.Text, QColor('#000000'))
        self.setPalette(palette)

        self._highlighter = None
        self._bracketHighlighter = BracketHighlighter()

        self._lines = Lines(self)

        self.completionThreshold = self._DEFAULT_COMPLETION_THRESHOLD
        self.completionEnabled = self._DEFAULT_COMPLETION_ENABLED
        self._completer = Completer(self)

        self._initActions()

        self._lineNumberArea = qutepart.sideareas.LineNumberArea(self)
        self._countCache = (-1, -1)
        self._markArea = qutepart.sideareas.MarkArea(self)

        self._bookmarks = qutepart.bookmarks.Bookmarks(self, self._markArea)

        self._userExtraSelections = []  # we draw bracket highlighting, current line and extra selections by user
        self._userExtraSelectionFormat = QTextCharFormat()
        self._userExtraSelectionFormat.setBackground(QBrush(QColor('#ffee00')))

        self.blockCountChanged.connect(self._updateLineNumberAreaWidth)
        self.updateRequest.connect(self._updateSideAreas)
        self.cursorPositionChanged.connect(self._updateExtraSelections)
        self.textChanged.connect(self._dropUserExtraSelections)
        self.textChanged.connect(self._resetCachedText)

        fontFamilies = {'Windows':'Courier New',
                        'Darwin': 'Menlo'}
        fontFamily = fontFamilies.get(platform.system(), 'Monospace')
        self.setFont(QFont(fontFamily))

        self._updateLineNumberAreaWidth(0)
        self._updateExtraSelections()

    def _initActions(self):
        """Init shortcuts for text editing
        """

        def createAction(text, shortcut, slot, iconFileName=None):
            """Create QAction with given parameters and add to the widget
            """
            action = QAction(text, self)
            if iconFileName is not None:
                action.setIcon(QIcon(getIconPath(iconFileName)))

            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.WidgetShortcut)
            action.triggered.connect(slot)

            self.addAction(action)

            return action

        self.scrollUpAction = createAction('Scroll up', 'Ctrl+Up',
                                           lambda: self._onShortcutScroll(down = False),
                                           'up.png')
        self.scrollDownAction = createAction('Scroll down', 'Ctrl+Down',
                                             lambda: self._onShortcutScroll(down = True),
                                             'down.png')
        self.selectAndScrollUpAction = createAction('Select and scroll Up', 'Ctrl+Shift+Up',
                                                    lambda: self._onShortcutSelectAndScroll(down = False))
        self.selectAndScrollDownAction = createAction('Select and scroll Down', 'Ctrl+Shift+Down',
                                                      lambda: self._onShortcutSelectAndScroll(down = True))
        self.decreaseIndentAction = createAction('Decrease indentation', 'Shift+Tab',
                            lambda: self._indenter.onChangeSelectedBlocksIndent(increase = False))
        self.autoIndentLineAction = createAction('Autoindent line', 'Ctrl+I',
                                                  self._indenter.onAutoIndentTriggered)
        self.moveLineUpAction = createAction('Move line up', 'Alt+Up',
                                             lambda: self._onShortcutMoveLine(down = False), 'up.png')
        self.moveLineDownAction = createAction('Move line down', 'Alt+Down',
                                               lambda: self._onShortcutMoveLine(down = True), 'down.png')
        self.deleteLineAction = createAction('Delete line', 'Alt+Del', self._onShortcutDeleteLine, 'deleted.png')
        self.copyLineAction = createAction('Copy line', 'Alt+C', self._onShortcutCopyLine, 'copy.png')
        self.pasteLineAction = createAction('Paste line', 'Alt+V', self._onShortcutPasteLine, 'paste.png')
        self.cutLineAction = createAction('Cut line', 'Alt+X', self._onShortcutCutLine, 'cut.png')
        self.duplicateLineAction = createAction('Duplicate line', 'Alt+D', self._onShortcutDuplicateLine)
        self.invokeCompletionAction = createAction('Invoke completion', 'Ctrl+Space', self._completer.invokeCompletion)
        self.printAction = createAction('Print', 'Ctrl+P', self._onShortcutPrint, 'print.png')
        self.indentWithSpaceAction = createAction('Indent with 1 space', 'Shift+Space',
                        lambda: self._indenter.onChangeSelectedBlocksIndent(increase=True,
                                                                              withSpace=True))
        self.unIndentWithSpaceAction = createAction('Unindent with 1 space', 'Shift+Backspace',
                            lambda: self._indenter.onChangeSelectedBlocksIndent(increase=False,
                                                                                  withSpace=True))

    def __enter__(self):
        """Context management method.
        Begin atomic modification
        """
        self._atomicModificationDepth = self._atomicModificationDepth + 1
        if self._atomicModificationDepth == 1:
            self.textCursor().beginEditBlock()

    def __exit__(self, exc_type, exc_value, traceback):
        """Context management method.
        End atomic modification
        """
        self._atomicModificationDepth = self._atomicModificationDepth - 1
        if self._atomicModificationDepth == 0:
            self.textCursor().endEditBlock()

        if exc_type is not None:
            return False

    def setFont(self, font):
        pass # suppress dockstring for non-public method
        """Set font and update tab stop width
        """
        QPlainTextEdit.setFont(self, font)
        self._updateTabStopWidth()

        # text on line numbers may overlap, if font is bigger, than code font
        self._lineNumberArea.setFont(font)

    def _updateTabStopWidth(self):
        """Update tabstop width after font or indentation changed
        """
        self.setTabStopWidth(self.fontMetrics().width(' ' * self._indenter.width))

    @property
    def lines(self):
        return self._lines

    @lines.setter
    def lines(self, value):
        if not isinstance(value, (list, tuple)) or \
           not all([isinstance(item, basestring) for item in value]):
            raise TypeError('Invalid new value of "lines" attribute')
        self.setPlainText('\n'.join(value))

    def _resetCachedText(self):
        """Reset toPlainText() result cache
        """
        self._cachedText = None

    @property
    def text(self):
        if self._cachedText is None:
            self._cachedText = self.toPlainText()

        return self._cachedText

    @text.setter
    def text(self, text):
        self.setPlainText(text)

    def textForSaving(self):
        """Get text with correct EOL symbols. Use this method for saving a file to storage
        """
        return self.eol.join(self.text.splitlines())

    @property
    def selectedText(self):
        text = self.textCursor().selectedText()

        # replace unicode paragraph separator with habitual \n
        text = text.replace(u'\u2029', '\n')

        return text

    @selectedText.setter
    def selectedText(self, text):
        self.textCursor().insertText(text)

    @property
    def cursorPosition(self):
        cursor = self.textCursor()
        return cursor.block().blockNumber(), cursor.positionInBlock()

    @cursorPosition.setter
    def cursorPosition(self, pos):
        line, col = pos

        line = min(line, len(self.lines) - 1)
        lineText = self.lines[line]

        if col is not None:
            col = min(col, len(lineText))
        else:
            col = len(lineText) - len(lineText.lstrip())

        cursor = QTextCursor(self.document().findBlockByNumber(line))
        cursor.setPositionInBlock(col)
        self.setTextCursor(cursor)

    @property
    def absCursorPosition(self):
        return self.textCursor().position()

    @absCursorPosition.setter
    def absCursorPosition(self, pos):
        cursor = self.textCursor()
        cursor.setPosition(pos)
        self.setTextCursor(cursor)

    @property
    def selectedPosition(self):
        cursor = self.textCursor()
        cursorLine, cursorCol = cursor.blockNumber(), cursor.positionInBlock()

        cursor.setPosition(cursor.anchor())
        startLine, startCol = cursor.blockNumber(), cursor.positionInBlock()

        return ((startLine, startCol), (cursorLine, cursorCol))

    @selectedPosition.setter
    def selectedPosition(self, pos):
        anchorPos, cursorPos = pos
        anchorLine, anchorCol = anchorPos
        cursorLine, cursorCol = cursorPos

        anchorCursor = QTextCursor(self.document().findBlockByNumber(anchorLine))
        anchorCursor.setPositionInBlock(anchorCol)

        # just get absolute position
        cursor = QTextCursor(self.document().findBlockByNumber(cursorLine))
        cursor.setPositionInBlock(cursorCol)

        anchorCursor.setPosition(cursor.position(), QTextCursor.KeepAnchor)
        self.setTextCursor(anchorCursor)

    @property
    def absSelectedPosition(self):
        cursor = self.textCursor()
        return cursor.anchor(), cursor.position()

    @absSelectedPosition.setter
    def absSelectedPosition(self, pos):
        anchorPos, cursorPos = pos
        cursor = self.textCursor()
        cursor.setPosition(anchorPos)
        cursor.setPosition(cursorPos, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)

    def resetSelection(self):
        """Reset selection. Nothing will be selected.
        """
        cursor = self.textCursor()
        cursor.setPosition(cursor.position())
        self.setTextCursor(cursor)

    @property
    def eol(self):
        return self._eol

    @eol.setter
    def eol(self, eol):
        if not eol in ('\r', '\n', '\r\n'):
            raise ValueError("Invalid EOL value")
        if eol != self._eol:
            self._eol = eol
            self.eolChanged.emit(self._eol)

    @property
    def indentWidth(self):
        return self._indenter.width

    @indentWidth.setter
    def indentWidth(self, width):
        if self._indenter.width != width:
            self._indenter.width = width
            self._updateTabStopWidth()
            self.indentWidthChanged.emit(width)

    @property
    def indentUseTabs(self):
        return self._indenter.useTabs

    @indentUseTabs.setter
    def indentUseTabs(self, use):
        if use != self._indenter.useTabs:
            self._indenter.useTabs = use
            self.indentUseTabsChanged.emit(use)

    def replaceText(self, pos, length, text):
        """Replace length symbols from ``pos`` with new text.

        If ``pos`` is an integer, it is interpreted as absolute position, if a tuple - as ``(line, column)``
        """
        if isinstance(pos, tuple):
            pos = self.mapToAbsPosition(*pos)

        endPos = pos + length

        if not self.document().findBlock(pos).isValid():
            raise IndexError('Invalid start position %d' % pos)

        if not self.document().findBlock(endPos).isValid():
            raise IndexError('Invalid end position %d' % endPos)

        cursor = QTextCursor(self.document())
        cursor.setPosition(pos)
        cursor.setPosition(endPos, QTextCursor.KeepAnchor)

        cursor.insertText(text)

    def insertText(self, pos, text):
        """Insert text at position

        If ``pos`` is an integer, it is interpreted as absolute position, if a tuple - as ``(line, column)``
        """
        return self.replaceText(pos, 0, text)

    def detectSyntax(self,
                     xmlFileName=None,
                     mimeType=None,
                     language=None,
                     sourceFilePath=None,
                     firstLine=None):
        """Get syntax by next parameters (fill as many, as known):

            * name of XML file with syntax definition
            * MIME type of source file
            * Programming language name
            * Source file path
            * First line of source file

        First parameter in the list has the hightest priority.
        Old syntax is always cleared, even if failed to detect new.

        Method returns ``True``, if syntax is detected, and ``False`` otherwise
        """
        oldLanguage = self.language()

        self.clearSyntax()

        syntax = self._globalSyntaxManager.getSyntax(SyntaxHighlighter.formatConverterFunction,
                                                     xmlFileName=xmlFileName,
                                                     mimeType=mimeType,
                                                     languageName=language,
                                                     sourceFilePath=sourceFilePath,
                                                     firstLine=firstLine)

        if syntax is not None:
            self._highlighter = SyntaxHighlighter(syntax, self.document())
            self._indenter.setSyntax(syntax)

        newLanguage = self.language()
        if oldLanguage != newLanguage:
            self.languageChanged.emit(newLanguage)

    def clearSyntax(self):
        """Clear syntax. Disables syntax highlighting

        This method might take long time, if document is big. Don't call it if you don't have to (i.e. in destructor)
        """
        if self._highlighter is not None:
            self._highlighter.del_()
            self._highlighter = None
            self.languageChanged.emit(None)

    def language(self):
        """Get current language name.
        Return ``None`` for plain text
        """
        if self._highlighter is None:
            return None
        else:
            return self._highlighter.syntax().name

    def isHighlightingInProgress(self):
        """Check if text highlighting is still in progress
        """
        return self._highlighter is not None and \
               self._highlighter.isInProgress()

    def isCode(self, blockOrBlockNumber, column):
        """Check if text at given position is a code.

        If language is not known, or text is not parsed yet, ``True`` is returned
        """
        if isinstance(blockOrBlockNumber, QTextBlock):
            block = blockOrBlockNumber
        else:
            block = self.document().findBlockByNumber(blockOrBlockNumber)

        return self._highlighter is None or \
               self._highlighter.isCode(block, column)

    def isComment(self, line, column):
        """Check if text at given position is a comment. Including block comments and here documents.

        If language is not known, or text is not parsed yet, ``False`` is returned
        """
        return self._highlighter is not None and \
               self._highlighter.isComment(self.document().findBlockByNumber(line), column)

    def isBlockComment(self, line, column):
        """Check if text at given position is a block comment.

        If language is not known, or text is not parsed yet, ``False`` is returned
        """
        return self._highlighter is not None and \
               self._highlighter.isBlockComment(self.document().findBlockByNumber(line), column)

    def isHereDoc(self, line, column):
        """Check if text at given position is a here document.

        If language is not known, or text is not parsed yet, ``False`` is returned
        """
        return self._highlighter is not None and \
               self._highlighter.isHereDoc(self.document().findBlockByNumber(line), column)

    def _dropUserExtraSelections(self):
        if self._userExtraSelections:
            self.setExtraSelections([])

    def setExtraSelections(self, selections):
        """Set list of extra selections.
        Selections are list of tuples ``(startAbsolutePosition, length)``.
        Extra selections are reset on any text modification.

        This is reimplemented method of QPlainTextEdit, it has different signature. Do not use QPlainTextEdit method
        """
        def _makeQtExtraSelection(startAbsolutePosition, length):
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(self.document())
            cursor.setPosition(startAbsolutePosition)
            cursor.setPosition(startAbsolutePosition + length, QTextCursor.KeepAnchor)
            selection.cursor = cursor
            selection.format = self._userExtraSelectionFormat
            return selection

        self._userExtraSelections = [_makeQtExtraSelection(*item) for item in selections]
        self._updateExtraSelections()

    def mapToAbsPosition(self, line, column):
        """Convert line and column number to absolute position
        """
        block = self.document().findBlockByNumber(line)
        if not block.isValid():
            raise IndexError("Invalid line index %d" % line)
        if column >= block.length():
            raise IndexError("Invalid column index %d" % column)
        return block.position() + column

    def mapToLineCol(self, absPosition):
        """Convert absolute position to ``(line, column)``
        """
        block = self.document().findBlock(absPosition)
        if not block.isValid():
            raise IndexError("Invalid absolute position %d" % absPosition)

        return (block.blockNumber(),
                absPosition - block.position())

    def _updateLineNumberAreaWidth(self, newBlockCount):
        """Set line number are width according to current lines count
        """
        self.setViewportMargins(self._lineNumberArea.width() + self._markArea.width(), 0, 0, 0)

    def _updateSideAreas(self, rect, dy):
        """Repaint line number area if necessary
        """
        # _countCache magic taken from Qt docs Code Editor Example
        if dy:
            self._lineNumberArea.scroll(0, dy)
            self._markArea.scroll(0, dy)
        elif self._countCache[0] != self.blockCount() or \
             self._countCache[1] != self.textCursor().block().lineCount():

            # if block height not added to rect, last line number sometimes is not drawn
            blockHeight = self.blockBoundingRect(self.firstVisibleBlock()).height()

            self._lineNumberArea.update(0, rect.y(), self._lineNumberArea.width(), rect.height() + blockHeight)
            self._lineNumberArea.update(0, rect.y(), self._markArea.width(), rect.height() + blockHeight)
        self._countCache = (self.blockCount(), self.textCursor().block().lineCount())

        if rect.contains(self.viewport().rect()):
            self._updateLineNumberAreaWidth(0)

    def resizeEvent(self, event):
        pass # suppress dockstring for non-public method
        """QWidget.resizeEvent() implementation.
        Adjust line number area
        """
        QPlainTextEdit.resizeEvent(self, event)

        cr = self.contentsRect()
        self._lineNumberArea.setGeometry(QRect(cr.left(), cr.top(), self._lineNumberArea.width(), cr.height()))

        self._markArea.setGeometry(QRect(cr.left() + self._lineNumberArea.width(),
                                         cr.top(),
                                         self._markArea.width(),
                                         cr.height()))

    def _insertNewBlock(self):
        """Enter pressed.
        Insert properly indented block
        """
        cursor = self.textCursor()
        with self:
            cursor.insertBlock()
            self._indenter.autoIndentBlock(cursor.block())
        self.ensureCursorVisible()

    def textBeforeCursor(self):
        pass  # suppress docstring for non-API method, used by internal classes
        """Text in current block from start to cursor position
        """
        cursor = self.textCursor()
        return cursor.block().text()[:cursor.positionInBlock()]

    def keyPressEvent(self, event):
        pass # suppress dockstring for non-public method
        """QPlainTextEdit.keyPressEvent() implementation.
        Catch events, which may not be catched with QShortcut and call slots
        """
        cursor = self.textCursor()

        def shouldUnindentWithBackspace():
            text = cursor.block().text()
            spaceAtStartLen = len(text) - len(text.lstrip())

            return self.textBeforeCursor().endswith(self._indenter.text()) and \
                   not cursor.hasSelection() and \
                   cursor.positionInBlock() == spaceAtStartLen

        def shouldAutoIndent(event):
            atEnd = cursor.positionInBlock() == cursor.block().length() - 1
            return atEnd and \
                   event.text() and \
                   event.text() in self._indenter.triggerCharacters()

        def backspaceOverwrite():
            with self:
                cursor.deletePreviousChar()
                cursor.insertText(' ')
                cursor.setPositionInBlock(cursor.positionInBlock() - 1)
                self.setTextCursor(cursor)

        def typeOverwrite(text):
            """QPlainTextEdit records text input in replace mode as 2 actions:
            delete char, and type char. Actions are undone separately. This is
            workaround for the Qt bug"""
            with self:
                cursor.deleteChar()
                cursor.insertText(text)

        if event.matches(QKeySequence.InsertParagraphSeparator):
            self._insertNewBlock()
        elif event.matches(QKeySequence.Copy) and self._rectangularSelection.isActive():
            self._rectangularSelection.copy()
        elif event.matches(QKeySequence.Cut) and self._rectangularSelection.isActive():
            self._rectangularSelection.cut()
        elif self._rectangularSelection.isDeleteKeyEvent(event):
            self._rectangularSelection.delete()
        elif event.key() == Qt.Key_Insert and event.modifiers() == Qt.NoModifier:
            self.setOverwriteMode(not self.overwriteMode())
        elif event.key() == Qt.Key_Tab and event.modifiers() == Qt.NoModifier:
            if cursor.hasSelection():
                self._indenter.onChangeSelectedBlocksIndent(increase=True)
            else:
                self._indenter.onShortcutIndentAfterCursor()
        elif event.key() == Qt.Key_Backspace and \
             shouldUnindentWithBackspace():
            self._indenter.onShortcutUnindentWithBackspace()
        elif event.key() == Qt.Key_Backspace and \
             not cursor.hasSelection() and \
             self.overwriteMode() and \
             cursor.positionInBlock() > 0:
            backspaceOverwrite()
        elif self.overwriteMode() and \
            event.text() and \
            event.text().isalnum() and \
            not cursor.hasSelection() and \
            cursor.positionInBlock() < cursor.block().length():
            typeOverwrite(event.text())
        elif event.matches(QKeySequence.MoveToStartOfLine):
            self._onShortcutHome(select=False)
        elif event.matches(QKeySequence.SelectStartOfLine):
            self._onShortcutHome(select=True)
        elif self._rectangularSelection.isExpandKeyEvent(event):
            self._rectangularSelection.onExpandKeyEvent(event)
        elif shouldAutoIndent(event):
                with self:
                    super(Qutepart, self).keyPressEvent(event)
                    self._indenter.autoIndentBlock(cursor.block(), event.text())
        else:
            # make action shortcuts override keyboard events (non-default Qt behaviour)
            for action in self.actions():
                seq = action.shortcut()
                if seq.count() == 1 and seq[0] == event.key() | int(event.modifiers()):
                    action.trigger()
                    break
            else:
                super(Qutepart, self).keyPressEvent(event)

    def mousePressEvent(self, mouseEvent):
        pass  # suppress docstring for non-public method
        if mouseEvent.modifiers() in RectangularSelection.MOUSE_MODIFIERS and \
           mouseEvent.button() == Qt.LeftButton:
            self._rectangularSelection.mousePressEvent(mouseEvent)
        else:
            super(Qutepart, self).mousePressEvent(mouseEvent)

    def mouseMoveEvent(self, mouseEvent):
        pass  # suppress docstring for non-public method
        if mouseEvent.modifiers() in RectangularSelection.MOUSE_MODIFIERS and \
           mouseEvent.buttons() == Qt.LeftButton:
            self._rectangularSelection.mouseMoveEvent(mouseEvent)
        else:
            super(Qutepart, self).mouseMoveEvent(mouseEvent)

    def _drawIndentMarkersAndEdge(self, paintEventRect):
        """Draw indentation markers
        """
        painter = QPainter(self.viewport())

        def cursorRect(block, column, offset):
            cursor = QTextCursor(block)
            cursor.setPositionInBlock(column)
            return self.cursorRect(cursor).translated(offset, 0)

        def drawWhiteSpace(block, column, char):
            leftCursorRect = cursorRect(block, column, 0)
            rightCursorRect = cursorRect(block, column + 1, 0)
            if leftCursorRect.top() == rightCursorRect.top():  # if on the same visual line
                middleHeight = (leftCursorRect.top() + leftCursorRect.bottom()) / 2
                if char == ' ':
                    painter.setPen(Qt.transparent)
                    painter.setBrush(QBrush(Qt.gray))
                    xPos = (leftCursorRect.x() + rightCursorRect.x()) / 2
                    painter.drawRect(QRect(xPos, middleHeight, 2, 2))
                else:
                    painter.setPen(QColor(Qt.gray).lighter(factor=120))
                    painter.drawLine(leftCursorRect.x() + 3, middleHeight,
                                     rightCursorRect.x() - 3, middleHeight)

        def effectiveEdgePos(text):
            """Position of edge in a block.
            Defined by self.lineLengthEdge, but visible width of \t is more than 1,
            therefore effective position depends on count and position of \t symbols
            Return -1 if line is too short to have edge
            """
            if self.lineLengthEdge is None:
                return -1

            tabExtraWidth = self.indentWidth - 1
            fullWidth = len(text) + (text.count('\t') * tabExtraWidth)
            if fullWidth <= self.lineLengthEdge:
                return -1

            currentWidth = 0
            for pos, char in enumerate(text):
                if char == '\t':
                    # Qt indents up to indentation level, so visible \t width depends on position
                    currentWidth += (self.indentWidth - (currentWidth % self.indentWidth))
                else:
                    currentWidth += 1
                if currentWidth > self.lineLengthEdge:
                    return pos
            else:  # line too narrow, probably visible \t width is small
                return -1

        def drawEdgeLine(block, edgePos):
            painter.setPen(QPen(QBrush(self.lineLengthEdgeColor), 0))
            rect = cursorRect(block, edgePos, 0)
            painter.drawLine(rect.topLeft(), rect.bottomLeft())

        def drawIndentMarker(block, column):
            painter.setPen(QColor(Qt.blue).lighter())
            rect = cursorRect(block, column, offset=0)
            painter.drawLine(rect.topLeft(), rect.bottomLeft())

        indentWidthChars = len(self._indenter.text())
        cursorPos = self.cursorPosition

        for block in iterateBlocksFrom(self.firstVisibleBlock()):
            blockGeometry = self.blockBoundingGeometry(block).translated(self.contentOffset())
            if blockGeometry.top() > paintEventRect.bottom():
                break

            if block.isVisible() and blockGeometry.toRect().intersects(paintEventRect):
                text = block.text()
                if not self.drawWhiteSpaceAnyIndentation:
                    # Draw indent markers
                    column = indentWidthChars
                    while text.startswith(self._indenter.text()) and \
                          len(text) > indentWidthChars and \
                          text[indentWidthChars].isspace():

                        if column != self.lineLengthEdge and \
                           (block.blockNumber(), column) != cursorPos:  # looks ugly, if both drawn
                            """on some fonts line is drawn below the cursor, if offset is 1
                            Looks like Qt bug"""
                            drawIndentMarker(block, column)

                        text = text[indentWidthChars:]
                        column += indentWidthChars

                # Draw edge, but not over a cursor
                edgePos = effectiveEdgePos(block.text())
                if edgePos != -1 and edgePos != cursorPos[1]:
                    drawEdgeLine(block, edgePos)

                text = block.text()
                lastNonSpaceColumn = len(text.rstrip()) - 1
                if self.drawWhiteSpaceTrailing or self.drawWhiteSpaceAnyIndentation:
                    # Draw whitespace symbols
                    text = block.text()
                    for column, char in enumerate(text):
                        if char.isspace():
                            if (char == '\t' or column == 0 or text[column - 1].isspace()) and \
                               self.drawWhiteSpaceAnyIndentation:
                                drawWhiteSpace(block, column, char)
                            elif column > lastNonSpaceColumn and self.drawWhiteSpaceTrailing:
                                drawWhiteSpace(block, column, char)

    def paintEvent(self, event):
        pass # suppress dockstring for non-public method
        """Paint event
        Draw indentation markers after main contents is drawn
        """
        super(Qutepart, self).paintEvent(event)
        self._drawIndentMarkersAndEdge(event.rect())

    def _currentLineExtraSelections(self):
        """QTextEdit.ExtraSelection, which highlightes current line
        """
        lineColor = QColor('#ffff99')
        def makeSelection(cursor):
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(lineColor)
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            cursor.clearSelection()
            selection.cursor = cursor
            return selection

        rectangularSelectionCursors = self._rectangularSelection.cursors()
        if rectangularSelectionCursors:
            return [makeSelection(cursor) \
                        for cursor in rectangularSelectionCursors]
        else:
            return [makeSelection(self.textCursor())]

    def _updateExtraSelections(self):
        """Highlight current line
        """
        cursorColumnIndex = self.textCursor().positionInBlock()

        bracketSelections = self._bracketHighlighter.extraSelections(self,
                                                                     self.textCursor().block(),
                                                                     cursorColumnIndex)

        allSelections = self._currentLineExtraSelections() + \
                        self._rectangularSelection.selections() + \
                        bracketSelections + \
                        self._userExtraSelections

        QPlainTextEdit.setExtraSelections(self, allSelections)

    def _onShortcutScroll(self, down):
        """Ctrl+Up/Down pressed, scroll viewport
        """
        value = self.verticalScrollBar().value()
        if down:
            value += 1
        else:
            value -= 1
        self.verticalScrollBar().setValue(value)

    def _onShortcutSelectAndScroll(self, down):
        """Ctrl+Shift+Up/Down pressed.
        Select line and scroll viewport
        """
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Down if down else QTextCursor.Up, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)
        self._onShortcutScroll(down)

    def _onShortcutHome(self, select):
        """Home pressed, move cursor to the line start or to the text start
        """
        cursor = self.textCursor()
        anchor = QTextCursor.KeepAnchor if select else QTextCursor.MoveAnchor
        text = cursor.block().text()
        spaceAtStartLen = len(text) - len(text.lstrip())
        if cursor.positionInBlock() == spaceAtStartLen:  # if at start of text
            cursor.setPositionInBlock(0, anchor)
        else:
            cursor.setPositionInBlock(spaceAtStartLen, anchor)
        self.setTextCursor(cursor)

    def _selectLines(self, startBlockNumber, endBlockNumber):
        """Select whole lines
        """
        startBlock = self.document().findBlockByNumber(startBlockNumber)
        endBlock = self.document().findBlockByNumber(endBlockNumber)
        cursor = QTextCursor(startBlock)
        cursor.setPosition(endBlock.position(), QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.setTextCursor(cursor)

    def _selectedBlocks(self):
        """Return selected blocks and tuple (startBlock, endBlock)
        """
        cursor = self.textCursor()
        return self.document().findBlock(cursor.selectionStart()), \
               self.document().findBlock(cursor.selectionEnd())

    def _selectedBlockNumbers(self):
        """Return selected block numbers and tuple (startBlockNumber, endBlockNumber)
        """
        startBlock, endBlock = self._selectedBlocks()
        return startBlock.blockNumber(), endBlock.blockNumber()

    def _onShortcutMoveLine(self, down):
        """Move line up or down
        Actually, not a selected text, but next or previous block is moved
        TODO keep bookmarks when moving
        """
        startBlock, endBlock = self._selectedBlocks()

        startBlockNumber = startBlock.blockNumber()
        endBlockNumber = endBlock.blockNumber()

        def _moveBlock(block, newNumber):
            text = block.text()
            with self:
                del self.lines[block.blockNumber()]
                self.lines.insert(newNumber, text)

        if down:  # move next block up
            blockToMove = endBlock.next()
            if not blockToMove.isValid():
                return

            # if operaiton is UnDone, marks are located incorrectly
            self._bookmarks.clear(startBlock, endBlock.next())

            _moveBlock(blockToMove, startBlockNumber)

            self._selectLines(startBlockNumber + 1, endBlockNumber + 1)
        else:  # move previous block down
            blockToMove = startBlock.previous()
            if not blockToMove.isValid():
                return

            # if operaiton is UnDone, marks are located incorrectly
            self._bookmarks.clear(startBlock.previous(), endBlock)

            _moveBlock(blockToMove, endBlockNumber)

            self._selectLines(startBlockNumber - 1, endBlockNumber - 1)

        self._markArea.update()

    def _selectedLinesSlice(self):
        """Get slice of selected lines
        """
        startBlockNumber, endBlockNumber = self._selectedBlockNumbers()
        return slice(startBlockNumber, endBlockNumber + 1, 1)

    def _onShortcutDeleteLine(self):
        """Delete line(s) under cursor
        """
        del self.lines[self._selectedLinesSlice()]

    def _onShortcutCopyLine(self):
        """Copy selected lines to the clipboard
        """
        lines = self.lines[self._selectedLinesSlice()]
        text = self._eol.join(lines)
        QApplication.clipboard().setText(text)

    def _onShortcutPasteLine(self):
        """Paste lines from the clipboard
        """
        lines = self.lines[self._selectedLinesSlice()]
        text = QApplication.clipboard().text()
        if text:
            with self:
                if self.textCursor().hasSelection():
                    startBlockNumber, endBlockNumber = self._selectedBlockNumbers()
                    del self.lines[self._selectedLinesSlice()]
                    self.lines.insert(startBlockNumber, text)
                else:
                    line, col = self.cursorPosition
                    if col > 0:
                        line = line + 1
                    self.lines.insert(line, text)

    def _onShortcutCutLine(self):
        """Cut selected lines to the clipboard
        """
        lines = self.lines[self._selectedLinesSlice()]

        self._onShortcutCopyLine()
        self._onShortcutDeleteLine()

    def _onShortcutDuplicateLine(self):
        """Duplicate selected text or current line
        """
        cursor = self.textCursor()
        if cursor.hasSelection():  # duplicate selection
            text = cursor.selectedText()
            selectionStart, selectionEnd = cursor.selectionStart(), cursor.selectionEnd()
            cursor.setPosition(selectionEnd)
            cursor.insertText(text)
            # restore selection
            cursor.setPosition(selectionStart)
            cursor.setPosition(selectionEnd, QTextCursor.KeepAnchor)
            self.setTextCursor(cursor)
        else:
            line = cursor.blockNumber()
            self.lines.insert(line + 1, self.lines[line])
            self.ensureCursorVisible()

        self._updateExtraSelections()  # newly inserted text might be highlighted as braces

    def _onShortcutPrint(self):
        """Ctrl+P handler.
        Show dialog, print file
        """
        dialog = QPrintDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            printer = dialog.printer()
            self.print_(printer)

    def insertFromMimeData(self, source):
        pass # suppress docstring for non-public method
        if source.hasFormat(self._rectangularSelection.MIME_TYPE):
            self._rectangularSelection.paste(source)
        else:
            super(Qutepart, self).insertFromMimeData(source)


def iterateBlocksFrom(block):
    """Generator, which iterates QTextBlocks from block until the End of a document
    """
    while block.isValid():
        yield block
        block = block.next()

def iterateBlocksBackFrom(block):
    """Generator, which iterates QTextBlocks from block until the Start of a document
    """
    while block.isValid():
        yield block
        block = block.previous()
