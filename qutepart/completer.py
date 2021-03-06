"""Autocompletion widget and logic
"""

import re
import time

from PyQt4.QtCore import pyqtSignal, QAbstractItemModel, QEvent, QModelIndex, QObject, QSize, Qt, QTimer, Qt
from PyQt4.QtGui import QCursor, QListView, QStyle

from qutepart.htmldelegate import HTMLDelegate

class _GlobalUpdateWordSetTimer:
    """Timer updates word set, when editor is idle. (5 sec. after last change)
    Timer is global, for avoid situation, when all instances
    update set simultaneously
    """
    _IDLE_TIMEOUT_MS = 1000

    def __init__(self):
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._onTimer)
        self._scheduledMethods = []

    def schedule(self, method):
        if not method in self._scheduledMethods:
            self._scheduledMethods.append(method)
        self._timer.start(self._IDLE_TIMEOUT_MS)

    def cancel(self, method):
        """Cancel scheduled method
        Safe method, may be called with not-scheduled method"""
        if method in self._scheduledMethods:
            self._scheduledMethods.remove(method)

        if not self._scheduledMethods:
            self._timer.stop()

    def _onTimer(self):
        method = self._scheduledMethods.pop()
        method()
        if self._scheduledMethods:
            self._timer.start(self._IDLE_TIMEOUT_MS)


class _CompletionModel(QAbstractItemModel):
    """QAbstractItemModel implementation for a list of completion variants

    words attribute contains all words
    canCompleteText attribute contains text, which may be inserted with tab
    """
    def __init__(self, wordSet):
        QAbstractItemModel.__init__(self)

        self._wordSet = wordSet

    def setData(self, wordBeforeCursor, wholeWord):
        """Set model information
        """
        self._typedText = wordBeforeCursor
        self.words = self._makeListOfCompletions(wordBeforeCursor, wholeWord)
        commonStart = self._commonWordStart(self.words)
        self.canCompleteText = commonStart[len(wordBeforeCursor):]

        self.layoutChanged.emit()

    def hasWords(self):
        return len(self.words) > 0

    def data(self, index, role):
        """QAbstractItemModel method implementation
        """
        if role == Qt.DisplayRole:
            text = self.words[index.row()]
            typed = text[:len(self._typedText)]
            canComplete = text[len(self._typedText):len(self._typedText) + len(self.canCompleteText)]
            rest = text[len(self._typedText) + len(self.canCompleteText):]
            if canComplete:
                # NOTE foreground colors are hardcoded, but I can't set background color of selected item (Qt bug?)
                # might look bad on some color themes
                return '<html>' \
                            '%s' \
                            '<font color="#e80000">%s</font>' \
                            '%s' \
                        '</html>' % (typed, canComplete, rest)
            else:
                return typed + rest
        else:
            return None

    def rowCount(self, index = QModelIndex()):
        """QAbstractItemModel method implementation
        """
        return len(self.words)

    def typedText(self):
        """Get current typed text
        """
        return self._typedText

    def _commonWordStart(self, words):
        """Get common start of all words.
        i.e. for ['blablaxxx', 'blablayyy', 'blazzz'] common start is 'bla'
        """
        if not words:
            return ''

        length = 0
        firstWord = words[0]
        otherWords = words[1:]
        for index, char in enumerate(firstWord):
            if not all([word[index] == char for word in otherWords]):
                break
            length = index + 1

        return firstWord[:length]

    def _makeListOfCompletions(self, wordBeforeCursor, wholeWord):
        """Make list of completions, which shall be shown
        """
        #krc: Case insensitive, not all programming languages are case-sensitive
        lc_word_before_cursor = wordBeforeCursor.lower()
        onlySuitable = [word for word in self._wordSet 
                        if ((len(lc_word_before_cursor) == 0) or
                            (word.lower().startswith(lc_word_before_cursor) and 
                             (word != wholeWord)))]
        return sorted(onlySuitable)

    """Trivial QAbstractItemModel methods implementation
    """
    def flags(self, index):                                 return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    def headerData(self, index):                            return None
    def columnCount(self, index):                           return 1
    def index(self, row, column, parent = QModelIndex()):   return self.createIndex(row, column)
    def parent(self, index):                                return QModelIndex()


class _CompletionList(QListView):
    """Completion list widget
    """
    closeMe = pyqtSignal()
    itemSelected = pyqtSignal(int)
    tabPressed = pyqtSignal()

    _MAX_VISIBLE_ROWS = 20  # no any technical reason, just for better UI

    def __init__(self, qpart, model):
        QListView.__init__(self, qpart.viewport())

        self.setAttribute(Qt.WA_DeleteOnClose)

        self.setItemDelegate(HTMLDelegate(self))

        self._qpart = qpart
        self.setFont(qpart.font())

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFocusPolicy(Qt.NoFocus)

        self.setModel(model)

        self._selectedIndex = -1

        # if cursor moved, we shall close widget, if its position (and model) hasn't been updated
        self._closeIfNotUpdatedTimer = QTimer(self)
        self._closeIfNotUpdatedTimer.setInterval(200)
        self._closeIfNotUpdatedTimer.setSingleShot(True)

        self._closeIfNotUpdatedTimer.timeout.connect(self._afterCursorPositionChanged)

        qpart.installEventFilter(self)

        qpart.cursorPositionChanged.connect(self._onCursorPositionChanged)

        self.clicked.connect(lambda index: self.itemSelected.emit(index.row()))

        self.updateGeometry()
        self.show()

        qpart.setFocus()

    def __del__(self):
        """Without this empty destructor Qt prints strange trace
            QObject::startTimer: QTimer can only be used with threads started with QThread
        when exiting
        """
        pass

    def close(self):
        """Explicitly called destructor.
        Removes widget from the qpart
        """
        self._closeIfNotUpdatedTimer.stop()
        self._qpart.removeEventFilter(self)
        self._qpart.cursorPositionChanged.disconnect(self._onCursorPositionChanged)

        QListView.close(self)

    def sizeHint(self):
        """QWidget.sizeHint implementation
        Automatically resizes the widget according to rows count

        FIXME very bad algorithm. Remove all this margins, if you can
        """
        width = max([self.fontMetrics().width(word) \
                        for word in self.model().words])
        width = width * 1.4  # FIXME bad hack. invent better formula
        width += 30  # margin

        # drawn with scrollbar without +2. I don't know why
        rowCount = min(self.model().rowCount(), self._MAX_VISIBLE_ROWS)
        height = self.sizeHintForRow(0) * (rowCount + 0.5)  # + 0.5 row margin

        return QSize(width, height)

    def minimumHeight(self):
        """QWidget.minimumSizeHint implementation
        """
        return self.sizeHintForRow(0) * 1.5  # + 0.5 row margin

    def _horizontalShift(self):
        """List should be plased such way, that typed text in the list is under
        typed text in the editor
        """
        strangeAdjustment = 2  # I don't know why. Probably, won't work on other systems and versions
        return self.fontMetrics().width(self.model().typedText()) + strangeAdjustment

    def updateGeometry(self):
        """Move widget to point under cursor
        """
        WIDGET_BORDER_MARGIN = 5
        SCROLLBAR_WIDTH = 30  # just a guess

        sizeHint = self.sizeHint()
        width = sizeHint.width()
        height = sizeHint.height()

        cursorRect = self._qpart.cursorRect()
        parentSize = self.parentWidget().size()

        spaceBelow = parentSize.height() - cursorRect.bottom() - WIDGET_BORDER_MARGIN
        spaceAbove = cursorRect.top() - WIDGET_BORDER_MARGIN

        if height <= spaceBelow or \
           spaceBelow > spaceAbove:
            yPos = cursorRect.bottom()
            if height > spaceBelow and \
               spaceBelow > self.minimumHeight():
                height = spaceBelow
                width = width + SCROLLBAR_WIDTH
        else:
            if height > spaceAbove and \
               spaceAbove > self.minimumHeight():
                height = spaceAbove
                width = width + SCROLLBAR_WIDTH
            yPos = max(3, cursorRect.top() - height)

        xPos = cursorRect.right() - self._horizontalShift()

        if xPos + width + WIDGET_BORDER_MARGIN > parentSize.width():
            xPos = max(3, parentSize.width() - WIDGET_BORDER_MARGIN - width)

        self.setGeometry(xPos, yPos, width, height)
        self._closeIfNotUpdatedTimer.stop()

    def _onCursorPositionChanged(self):
        """Cursor position changed. Schedule closing.
        Timer will be stopped, if widget position is being updated
        """
        self._closeIfNotUpdatedTimer.start()

    def _afterCursorPositionChanged(self):
        """Widget position hasn't been updated after cursor position change, close widget
        """
        self.closeMe.emit()

    def eventFilter(self, object, event):
        """Catch events from qpart
        Move selection, select item, or close themselves
        """
        if event.type() == QEvent.KeyPress and event.modifiers() == Qt.NoModifier:
            if event.key() == Qt.Key_Escape:
                self.closeMe.emit()
                return True
            elif event.key() == Qt.Key_Down:
                if self._selectedIndex + 1 < self.model().rowCount():
                    self._selectItem(self._selectedIndex + 1)
                return True
            elif event.key() == Qt.Key_Up:
                if self._selectedIndex - 1 >= 0:
                    self._selectItem(self._selectedIndex - 1)
                return True
            elif event.key() in (Qt.Key_Enter, Qt.Key_Return):
                if self._selectedIndex != -1:
                    self.itemSelected.emit(self._selectedIndex)
                    return True
            elif event.key() == Qt.Key_Tab:
                self.tabPressed.emit()
                return True
        elif event.type() == QEvent.FocusOut:
            self.closeMe.emit()

        return False

    def _selectItem(self, index):
        """Select item in the list
        """
        self._selectedIndex = index
        self.setCurrentIndex(self.model().createIndex(index, 0))


class Completer(QObject):
    """Object listens Qutepart widget events, computes and shows autocompletion lists
    """
    _globalUpdateWordSetTimer = _GlobalUpdateWordSetTimer()

    _WORD_SET_UPDATE_MAX_TIME_SEC = 0.4
    #krc: Keyword arguments pythonically passed to Completer from outside QutePart
    def __init__(self, qpart, ContentAutoComplete=True, WordList=None, ParentChildDict=None):
        QObject.__init__(self, qpart)

        self._qpart = qpart
        self._widget = None
        self._completionOpenedManually = False

        self._wordSet = None
        #krc: Block word sets based on document content if:
        #krc: 1) The programmer disables it
        #krc: 2) A static word list is provided, e.g. SQL keywords
        #krc: 3) A parent/child dictionary is provided, e.g. table.column
        self._ContentAutoComplete = \
            (ContentAutoComplete and (WordList is None) and (ParentChildDict is None))
        #krc: Use after-instantiation update mechanism to initialize completer 
        self.updateWordList(WordList)
        self.updateParentChildDict(ParentChildDict)

        qpart.installEventFilter(self)
        qpart.textChanged.connect(self._onTextChanged)

        self.destroyed.connect(self.del_)

    def del_(self):
        """Object deleted. Cancel timer
        """
        self._globalUpdateWordSetTimer.cancel(self._updateWordSet)

    def _onTextChanged(self):
        """Text in the qpart changed. Update word set"""
        #krc: Block word sets based on document content
        if (not self._ContentAutoComplete): return
        self._globalUpdateWordSetTimer.schedule(self._updateWordSet)

    def _updateWordSet(self):
        """Make a set of words, which shall be completed, from text
        """
        #krc: Block word sets based on document content
        if (not self._ContentAutoComplete): return
        self._wordSet = set()

        start = time.time()

        for line in self._qpart.lines:
            for match in self._wordRegExp.findall(line):
                self._wordSet.add(match)
            if time.time() - start > self._WORD_SET_UPDATE_MAX_TIME_SEC:
                """It is better to have incomplete word set, than to freeze the GUI"""
                break

    #krc: Dynamic changes to static WordList, ...
    #krc: ...potentially different database entities to autocomplete
    def updateWordList(self, WordList):
        if (WordList is None):
            self._wordSet = None
        else:
            self._wordSet = set()
            for word in WordList:
                self._wordSet.add(word)

    #krc: Dynamic changes to ParentChildDict, ...
    #krc: ...potentially different database entities to autocomplete
    def updateParentChildDict(self, ParentChildDict):
        if (ParentChildDict is None):
            self._parentChildDict = None
            #krc: Detect end of 'identifier'
            #krc: This is the same as your code except the RegEx is not shared (global).
            #krc: Each completer instance may have a different word definition.
            self._wordPattern = "\w+"
            self._wordRegExp = re.compile(self._wordPattern)
            self._wordAtEndRegExp = re.compile(self._wordPattern + '$')
            self._wordAtStartRegExp = re.compile('^' + self._wordPattern)
        else:
            self._parentChildDict = {}
            for parent, child_list in ParentChildDict.items():
                child_set = set()
                for child in child_list:
                    child_set.add(child)
                self._parentChildDict[parent] = child_set
    
            #krc: Detect end of 'identifier' OR 'identifier.'
            self._wordPattern = "\w+[.]?\w*"
            self._wordRegExp = re.compile(self._wordPattern)
            self._wordAtEndRegExp = re.compile(self._wordPattern + '$')
            self._wordAtStartRegExp = re.compile('^' + self._wordPattern)

    def invokeCompletion(self):
        """Invoke completion manually"""
        if self._invokeCompletionIfAvailable(requestedByUser=True):
            self._completionOpenedManually = True

    def eventFilter(self, object, event):
        """Catch events from qpart. Show completion if necessary
        """
        if event.type() == QEvent.KeyRelease:
            text = event.text()
            textTyped = ((event.modifiers() in (Qt.NoModifier, Qt.ShiftModifier)) and 
                         # Detect 'identifier' in most programming languages
                         (text.isalpha() or text.isdigit() or (text == '_') or
                          #krc: Detect end of 'identifier' OR 'identifier.'
                          ((text == '.') and (self._parentChildDict is not None))))
            if textTyped or \
            (event.key() == Qt.Key_Backspace and self._widget is not None):
                self._invokeCompletionIfAvailable()
                return False

        return False

    def _invokeCompletionIfAvailable(self, requestedByUser=False):
        """Invoke completion, if available. Called after text has been typed in qpart
        Returns True, if invoked
        """
        if (self._qpart.completionEnabled and 
            ((self._wordSet is not None) or (self._parentChildDict is not None))):
            wordBeforeCursor = self._wordBeforeCursor()
            wholeWord = wordBeforeCursor + self._wordAfterCursor()

            #krc: ParentChildDict
            #krc: Here we have to look for two things, a parent identifier, ...
            #krc: for example, a table name which yields a word list... 
            #krc: ...consisting of column names. This list is narrowed down...
            #krc: ...as the user types characters after the dot.
            #krc: This is a dynamic word set based on the identifier before the dot.
            if (('.' in wordBeforeCursor) and 
                (len(wordBeforeCursor.split('.')[0]) >= 2) and 
                (len(wordBeforeCursor.split('.')[1]) >= 0)):
                if ((self._parentChildDict is not None) and
                    (wordBeforeCursor.split('.')[0] in self._parentChildDict)):
                    child_set = self._parentChildDict[wordBeforeCursor.split('.')[0]]
                    if self._widget is None:
                        model = _CompletionModel(child_set)
                        model.setData(wordBeforeCursor.split('.')[1], wholeWord)
                        if model.hasWords():
                            self._widget = _CompletionList(self._qpart, model)
                            self._widget.closeMe.connect(self._closeCompletion)
                            self._widget.itemSelected.connect(self._onCompletionListItemSelected)
                            self._widget.tabPressed.connect(self._onCompletionListTabPressed)
                            return True
                    else:
                        self._widget.model().setData(wordBeforeCursor.split('.')[1], wholeWord)
                        if self._widget.model().hasWords():
                            self._widget.updateGeometry()
                            return True

            elif (wordBeforeCursor and (self._wordSet is not None)):
                #krc: This implements a static word set based on reserved words, etc.
                if len(wordBeforeCursor) >= self._qpart.completionThreshold or \
                   self._completionOpenedManually or \
                   requestedByUser:
                    if self._widget is None:
                        model = _CompletionModel(self._wordSet)
                        model.setData(wordBeforeCursor, wholeWord)
                        if model.hasWords():
                            self._widget = _CompletionList(self._qpart, model)
                            self._widget.closeMe.connect(self._closeCompletion)
                            self._widget.itemSelected.connect(self._onCompletionListItemSelected)
                            self._widget.tabPressed.connect(self._onCompletionListTabPressed)
                            return True
                    else:
                        self._widget.model().setData(wordBeforeCursor, wholeWord)
                        if self._widget.model().hasWords():
                            self._widget.updateGeometry()
                            return True

        self._closeCompletion()
        return False

    def _closeCompletion(self):
        """Close completion, if visible.
        Delete widget
        """
        if self._widget is not None:
            self._widget.close()
            self._widget = None
            self._completionOpenedManually = False

    def _wordBeforeCursor(self):
        """Get word, which is located before cursor
        """
        cursor = self._qpart.textCursor()
        textBeforeCursor = cursor.block().text()[:cursor.positionInBlock()]
        match = self._wordAtEndRegExp.search(textBeforeCursor)
        if match:
            return match.group(0)
        else:
            return ''

    def _wordAfterCursor(self):
        """Get word, which is located before cursor
        """
        cursor = self._qpart.textCursor()
        textAfterCursor = cursor.block().text()[cursor.positionInBlock():]
        match = self._wordAtStartRegExp.search(textAfterCursor)
        if match:
            return match.group(0)
        else:
            return ''

    def _onCompletionListItemSelected(self, index):
        """Item selected. Insert completion to editor
        """
        model = self._widget.model()
        selectedWord = model.words[index]
        textToInsert = selectedWord[len(model.typedText()):]
        self._qpart.textCursor().insertText(textToInsert)
        self._closeCompletion()

    def _onCompletionListTabPressed(self):
        """Tab pressed on completion list
        Insert completable text, if available
        """
        canCompleteText = self._widget.model().canCompleteText
        if canCompleteText:
            self._qpart.textCursor().insertText(canCompleteText)
            self._invokeCompletionIfAvailable()
