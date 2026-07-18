from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QStyledItemDelegate, QStyle, QApplication, QListWidget,
    QGraphicsOpacityEffect, QListWidgetItem
)
from PyQt6.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QFont, QPalette, QPen, QFontMetrics
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QSize
)

from utils import get_circular_pixmap


class BubbleWidget(QFrame):
    def __init__(self, is_self, parent=None):
        super().__init__(parent)
        self.setObjectName("bubbleWidget")
        self.is_self = is_self
        self.is_highlighted = False
        self.group_pos = "single"
        self.update_style()
        
    def set_group_pos(self, pos):
        if getattr(self, "group_pos", None) != pos:
            self.group_pos = pos
            self.update_style()
            
    def update_style(self):
        if self.is_self:
            bg_color = QApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
        else:
            bg_color = QApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Button)
            if bg_color.lightness() < 128:
                bg_color = bg_color.lighter(130)
            else:
                bg_color = bg_color.darker(110)
                
        if self.is_highlighted:
            bg_color = bg_color.lighter(130)
            
        tl = tr = bl = br = 16
        if self.is_self:
            if getattr(self, "group_pos", "single") == "single":
                br = 4
            elif self.group_pos == "top":
                br = 4
            elif self.group_pos == "middle":
                tr = 4
                br = 4
            elif self.group_pos == "bottom":
                tr = 4
        else:
            if getattr(self, "group_pos", "single") == "single":
                bl = 4
            elif self.group_pos == "top":
                bl = 4
            elif self.group_pos == "middle":
                tl = 4
                bl = 4
            elif self.group_pos == "bottom":
                tl = 4
                
        self.setStyleSheet(f"""
            #bubbleWidget {{
                background-color: {bg_color.name()};
                border-top-left-radius: {tl}px;
                border-top-right-radius: {tr}px;
                border-bottom-left-radius: {bl}px;
                border-bottom-right-radius: {br}px;
            }}
        """)


class InputContainerWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pal = self.palette()
        bg_color = pal.color(QPalette.ColorRole.Base)
        if bg_color.lightness() < 128:
            bg_color = bg_color.lighter(130)
        else:
            bg_color = bg_color.darker(105)
            
        painter.setBrush(bg_color)
        painter.setPen(pal.color(QPalette.ColorRole.Mid))
        painter.drawRoundedRect(self.rect(), 24, 24)


class SendButton(QPushButton):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pal = self.palette()
        if self.isDown():
            bg_color = pal.color(QPalette.ColorRole.Highlight).darker(110)
        elif self.underMouse():
            bg_color = pal.color(QPalette.ColorRole.Highlight)
        else:
            bg_color = pal.color(QPalette.ColorRole.Button)
            
        painter.setBrush(bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 16, 16)
        
        painter.setPen(pal.color(QPalette.ColorRole.ButtonText))
        font = painter.font()
        font.setPixelSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class QuoteFrame(QFrame):
    clicked = pyqtSignal(str)
    def __init__(self, msg_id, parent=None):
        super().__init__(parent)
        self.msg_id = msg_id
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.msg_id:
            self.clicked.emit(self.msg_id)
        super().mousePressEvent(event)


class MessageWidget(QWidget):
    reply_clicked = pyqtSignal(int)
    
    def __init__(self, content, is_self, avatar_path=None, reply_data=None, animate=False, sender_id=None, timestamp=None):
        super().__init__()
        self.should_animate = animate
        self.sender_id = sender_id
        self.timestamp = timestamp
        self._viewport_width = 800
        
        self.main_layout = QHBoxLayout()
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        
        if self.should_animate:
            self.fade_eff = QGraphicsOpacityEffect(self)
            self.setGraphicsEffect(self.fade_eff)
            
            self.fade_anim = QPropertyAnimation(self.fade_eff, b"opacity")
            self.fade_anim.setDuration(400)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)
            self.fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
            self.fade_anim.finished.connect(self._on_fade_finished)
            self._fade_cleaned_up = False
        
        message_column = QVBoxLayout()
        message_column.setSpacing(4)
        
        if reply_data:
            replier_name = "You" if is_self else reply_data.get('sender', 'They')
            replier_lbl = QLabel(f"{replier_name} replied")
            replier_lbl.setStyleSheet("color: palette(placeholderText); font-size: 12px; font-weight: bold;")
            replier_lbl.setAlignment(Qt.AlignmentFlag.AlignRight if is_self else Qt.AlignmentFlag.AlignLeft)
            message_column.addWidget(replier_lbl)
            
            quote_frame = QuoteFrame(reply_data.get("id"))
            quote_frame.setCursor(Qt.CursorShape.PointingHandCursor)
            quote_frame.clicked.connect(self.reply_clicked.emit)
            quote_frame.setStyleSheet("""
                QFrame {
                    background-color: #2b2b2b;
                    border-radius: 16px;
                }
            """)
            quote_layout = QHBoxLayout()
            quote_layout.setContentsMargins(14, 10, 14, 10)
            quote_layout.setSpacing(10)
            
            quote_text = reply_data.get('content', '')
            quote_lbl = QLabel(quote_text)
            quote_lbl.setStyleSheet("color: #cccccc; font-size: 13px;")
            quote_lbl.setWordWrap(True)
            min_w_quote = min(500, len(quote_text) * 7)
            if min_w_quote > 100:
                quote_lbl.setMinimumWidth(min_w_quote)
            
            bar = QFrame()
            bar.setFixedWidth(4)
            bar.setStyleSheet("background-color: #4a4a4a; border-radius: 2px;")
            
            if is_self:
                quote_layout.addWidget(quote_lbl)
                quote_layout.addWidget(bar)
            else:
                quote_layout.addWidget(bar)
                quote_layout.addWidget(quote_lbl)
                
            quote_frame.setLayout(quote_layout)
            
            quote_container = QHBoxLayout()
            quote_container.setContentsMargins(0,0,0,0)
            if is_self:
                quote_container.addStretch()
                quote_container.addWidget(quote_frame)
            else:
                quote_container.addWidget(quote_frame)
                quote_container.addStretch()
                
            message_column.addLayout(quote_container)
            
        bubble_layout = QVBoxLayout()
        bubble_layout.setContentsMargins(14, 10, 14, 10)
        
        self.raw_content = content
        self.content_lbl = QLabel(content)
        self.content_lbl.setWordWrap(True)
        
        self.content_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.content_lbl.setCursor(Qt.CursorShape.IBeamCursor)
        
        if is_self:
            active_text = QApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.HighlightedText).name()
            self.content_lbl.setStyleSheet(f"color: {active_text}; font-size: 14px; selection-background-color: white; selection-color: black;")
        else:
            active_text = QApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.WindowText).name()
            self.content_lbl.setStyleSheet(f"color: {active_text}; font-size: 14px; selection-background-color: palette(highlight); selection-color: palette(highlighted-text);")
            
        bubble_layout.addWidget(self.content_lbl)
        
        self.bubble_container = BubbleWidget(is_self)
        self.bubble_container.setLayout(bubble_layout)
        
        bubble_align_layout = QHBoxLayout()
        bubble_align_layout.setContentsMargins(0,0,0,0)
        if is_self:
            bubble_align_layout.addStretch()
            bubble_align_layout.addWidget(self.bubble_container)
        else:
            bubble_align_layout.addWidget(self.bubble_container)
            bubble_align_layout.addStretch()
            
        message_column.addLayout(bubble_align_layout)
        
        self.avatar_lbl = None
        self._avatar_pixmap = None
        if is_self:
            self.main_layout.addStretch()
            self.main_layout.addLayout(message_column)
        else:
            self.avatar_lbl = QLabel()
            if avatar_path:
                self._avatar_pixmap = get_circular_pixmap(avatar_path, 32)
                self.avatar_lbl.setPixmap(self._avatar_pixmap)
            self.avatar_lbl.setFixedSize(32, 32)
            self.main_layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)
            self.main_layout.addLayout(message_column)
            self.main_layout.addStretch()
            
        self.setLayout(self.main_layout)
        

    def set_group_pos(self, pos):
        if hasattr(self, 'bubble_container'):
            self.bubble_container.set_group_pos(pos)
            
        top_margin = 1 if pos in ("middle", "bottom") else 6
        bottom_margin = 1 if pos in ("top", "middle") else 6
        self.main_layout.setContentsMargins(4, top_margin, 4, bottom_margin)
        
        if self.avatar_lbl and self._avatar_pixmap:
            if pos in ("single", "top"):
                self.avatar_lbl.setPixmap(self._avatar_pixmap)
            else:
                empty = QPixmap(32, 32)
                empty.fill(Qt.GlobalColor.transparent)
                self.avatar_lbl.setPixmap(empty)

    def update_width(self, w):
        max_w = int(w * 0.75)
        if hasattr(self, 'raw_content'):
            font = self.content_lbl.font()
            font.setPixelSize(14)
            from PyQt6.QtGui import QTextDocument
            doc = QTextDocument(self.raw_content)
            doc.setDefaultFont(font)
            doc.setDocumentMargin(0)
            doc.setTextWidth(max_w)
            
            import math
            ideal_w = math.ceil(doc.idealWidth())
            self.content_lbl.setFixedWidth(min(ideal_w, max_w))
        if hasattr(self, 'bubble_container'):
            self.bubble_container.setMaximumWidth(max_w)

    def _on_fade_finished(self):
        if not self._fade_cleaned_up:
            self._fade_cleaned_up = True
            self.setGraphicsEffect(None)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.should_animate and hasattr(self, 'fade_anim') and not self._fade_cleaned_up:
            self.fade_anim.stop()
            self._fade_cleaned_up = True
            self.fade_anim.disconnect()

    def showEvent(self, event):
        super().showEvent(event)
        if self.should_animate:
            self.fade_anim.start()
            
    def trigger_highlight(self):
        if hasattr(self, 'bubble_container'):
            self.bubble_container.is_highlighted = True
            self.bubble_container.update_style()
            QTimer.singleShot(1000, self._remove_highlight)
            
    def _remove_highlight(self):
        if hasattr(self, 'bubble_container'):
            self.bubble_container.is_highlighted = False
            self.bubble_container.update_style()


class ConversationWidget(QWidget):
    def __init__(self, title, preview_text, avatar_path=None, presence_type=0, unread=False):
        super().__init__()
        
        inner_layout = QHBoxLayout()
        inner_layout.setContentsMargins(12, 12, 12, 12)
        inner_layout.setSpacing(14)
        
        avatar_lbl = QLabel()
        avatar_lbl.setPixmap(get_circular_pixmap(avatar_path, 40, presence_type, unread))
        avatar_lbl.setFixedSize(40, 40)
        
        if presence_type is not None:
            presence_texts = {0: "Offline", 1: "Website", 2: "In Game", 3: "Studio"}
            avatar_lbl.setToolTip(presence_texts.get(presence_type, "Unknown"))
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        
        title_lbl = QLabel(title)
        font = QFont("Segoe UI", 11)
        font.setBold(unread)
        title_lbl.setFont(font)
        title_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        preview_lbl = QLabel()
        preview_lbl.setFont(QFont("Segoe UI", 10))
        preview_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        metrics = preview_lbl.fontMetrics()
        preview_text = preview_text.replace("\n", " ")
        elided = metrics.elidedText(preview_text, Qt.TextElideMode.ElideRight, 170)
        preview_lbl.setText(elided)
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(preview_lbl)
        text_layout.addStretch()
        
        inner_layout.addWidget(avatar_lbl)
        inner_layout.addLayout(text_layout)
        inner_layout.addStretch()
        
        self.setLayout(inner_layout)


class ChatListDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = option.rect
        
        if option.state & QStyle.StateFlag.State_Selected:
            bg_color = QApplication.palette().color(QPalette.ColorGroup.Active, QPalette.ColorRole.Highlight)
            painter.setBrush(QColor(bg_color.red(), bg_color.green(), bg_color.blue(), 80))
            painter.setPen(Qt.PenStyle.NoPen)
            hl_rect = rect.adjusted(4, 4, -4, -4)
            painter.drawRoundedRect(hl_rect, 12, 12)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setBrush(QColor(128, 128, 128, 25))
            painter.setPen(Qt.PenStyle.NoPen)
            hl_rect = rect.adjusted(4, 4, -4, -4)
            painter.drawRoundedRect(hl_rect, 12, 12)
            
        painter.setPen(QPen(QColor(128, 128, 128, 40), 1))
        painter.drawLine(rect.left() + 16, rect.bottom(), rect.right() - 16, rect.bottom())
        
        painter.restore()
