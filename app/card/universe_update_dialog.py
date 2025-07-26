from PyQt5.QtCore import QTimer, pyqtSignal
from qfluentwidgets import BodyLabel
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import ProgressBar

from .messagebox_custom import MessageBoxUpdate


class UniverseUpdateDialog(MessageBoxUpdate):
    """模拟宇宙更新对话框，支持显示更新信息、进度和取消功能"""
    
    updateRequested = pyqtSignal()  # 点击更新按钮的信号
    cancelRequested = pyqtSignal()  # 点击取消按钮的信号
    
    def __init__(self, title, content, parent=None):
        super().__init__(title, content, parent)
        self.is_updating = False
        self.setupCustomUI()
        
    def setupCustomUI(self):
        """设置自定义UI界面"""
        self.yesButton.setText("立即更新")
        self.yesButton.setIcon(FIF.UPDATE.icon())
        self.cancelButton.setText("取消")
        self.cancelButton.setIcon(FIF.CANCEL.icon())
        
        # 断开原有信号连接，连接自定义处理
        self.yesButton.clicked.disconnect()
        self.cancelButton.clicked.disconnect()
        self.yesButton.clicked.connect(self.on_update_clicked)
        self.cancelButton.clicked.connect(self.on_cancel_clicked)
        
        # 添加状态标签
        self.status_label = BodyLabel("准备更新...")
        self.textLayout.addWidget(self.status_label)
        
        # 添加进度条
        self.progress_bar = ProgressBar()
        self.progress_bar.setVisible(False)
        self.textLayout.addWidget(self.progress_bar)
    def on_update_clicked(self):
        """处理更新按钮点击"""
        if not self.is_updating:
            # 开始更新
            self.is_updating = True
            self.yesButton.setText("正在更新...")
            self.yesButton.setEnabled(False)
            self.progress_bar.setVisible(True)
            self.status_label.setText("正在下载更新...")
            self.updateRequested.emit()
        
    def on_cancel_clicked(self):
        """处理取消按钮点击"""
        if self.is_updating:
            # 取消更新
            self.cancelButton.setText("正在取消...")
            self.cancelButton.setEnabled(False)
            self.status_label.setText("正在取消下载...")
            self.cancelRequested.emit()
        else:
            # 直接关闭对话框
            self.reject()
            
    def update_progress(self, value):
        """更新进度"""
        self.progress_bar.setValue(value)
        
    def update_status(self, status):
        """更新状态文本"""
        self.status_label.setText(status)
        
    def update_completed(self, success=True, message=""):
        """更新完成"""
        self.is_updating = False
        self.progress_bar.setVisible(False)
        
        if success:
            self.status_label.setText("更新完成！")
            self.yesButton.setText("完成")
            self.yesButton.setEnabled(False)
            self.cancelButton.setText("关闭")
            self.cancelButton.setEnabled(True)
            # 3秒后自动关闭
            QTimer.singleShot(3000, self.accept)
        else:
            self.status_label.setText(f"更新失败：{message}")
            self.yesButton.setText("重试")
            self.yesButton.setEnabled(True)
            self.cancelButton.setText("关闭")
            self.cancelButton.setEnabled(True)
            
    def update_cancelled(self):
        """更新被取消"""
        self.is_updating = False
        self.progress_bar.setVisible(False)
        self.status_label.setText("更新已取消")
        self.yesButton.setText("立即更新")
        self.yesButton.setEnabled(True)
        self.cancelButton.setText("关闭")
        self.cancelButton.setEnabled(True)
        self.cancelButton.setText("关闭")
        self.cancelButton.setEnabled(True)
