from contextlib import redirect_stdout

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

with redirect_stdout(None):
    from qfluentwidgets import NavigationItemPosition, MSFluentWindow, SplashScreen, setThemeColor, NavigationBarPushButton, toggleTheme, setTheme, Theme
    from qfluentwidgets import FluentIcon as FIF
    from qfluentwidgets import InfoBar, InfoBarPosition

import base64

from module.config import cfg
from utils.gamecontroller import GameController

from .card.messagebox_custom import MessageBoxSupport
from .help_interface import HelpInterface
from .home_interface import HomeInterface
from .setting_interface import SettingInterface
from .tools.announcement import checkAnnouncement
from .tools.check_theme_change import checkThemeChange
from .tools.check_update import checkUniverseUpdate, checkUpdate
from .tools.disclaimer import disclaimer
from .tools_interface import ToolsInterface
# from .changelog_interface import ChangelogInterface
from .warp_interface import WarpInterface


class MainWindow(MSFluentWindow):
    def __init__(self):
        super().__init__()
        self.initWindow()

        self.initInterface()
        self.initNavigation()

        # 检查更新
        checkUpdate(self, flag=True)
        # 检查模拟宇宙更新
        checkUniverseUpdate(self, flag=True)
        checkAnnouncement(self)

    def initWindow(self):
        self.setMicaEffectEnabled(False)
        setThemeColor('#f18cb9', lazy=True)
        setTheme(Theme.AUTO, lazy=True)

        # 禁用最大化
        self.titleBar.maxBtn.setHidden(True)
        self.titleBar.maxBtn.setDisabled(True)
        self.titleBar.setDoubleClickEnabled(False)
        self.setResizeEnabled(False)
        self.setWindowFlags(Qt.WindowCloseButtonHint)
        # self.setWindowFlags(Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)

        self.resize(960, 640)
        self.setWindowIcon(QIcon('./assets/logo/March7th.ico'))
        self.setWindowTitle("March7th Assistant")

        # 创建启动画面
        self.splashScreen = SplashScreen(self.windowIcon(), self)
        self.splashScreen.setIconSize(QSize(128, 128))
        self.splashScreen.titleBar.maxBtn.setHidden(True)
        self.splashScreen.raise_()

        desktop = QApplication.desktop().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

        self.show()
        QApplication.processEvents()

    def initInterface(self):
        self.homeInterface = HomeInterface(self)
        self.helpInterface = HelpInterface(self)
        # self.changelogInterface = ChangelogInterface(self)
        self.warpInterface = WarpInterface(self)
        self.toolsInterface = ToolsInterface(self)
        self.settingInterface = SettingInterface(self)

    def initNavigation(self):
        self.addSubInterface(self.homeInterface, FIF.HOME, self.tr('主页'))
        self.addSubInterface(self.helpInterface, FIF.BOOK_SHELF, self.tr('帮助'))
        # self.addSubInterface(self.changelogInterface, FIF.UPDATE, self.tr('更新日志'))
        self.addSubInterface(self.warpInterface, FIF.SHARE, self.tr('抽卡记录'))
        self.addSubInterface(self.toolsInterface, FIF.DEVELOPER_TOOLS, self.tr('工具箱'))

        self.navigationInterface.addWidget(
            'startGameButton',
            NavigationBarPushButton(FIF.PLAY, '启动游戏', isSelectable=False),
            self.startGame,
            NavigationItemPosition.BOTTOM)

        self.navigationInterface.addWidget(
            'themeButton',
            NavigationBarPushButton(FIF.BRUSH, '主题', isSelectable=False),
            lambda: toggleTheme(lazy=True),
            NavigationItemPosition.BOTTOM)

        self.navigationInterface.addWidget(
            'avatar',
            NavigationBarPushButton(FIF.HEART, '赞赏', isSelectable=False),
            lambda: MessageBoxSupport(
                '支持作者🥰',
                '此程序为免费开源项目，如果你付了钱请立刻退款\n如果喜欢本项目，可以微信赞赏送作者一杯咖啡☕\n您的支持就是作者开发和维护项目的动力🚀',
                './assets/app/images/sponsor.jpg',
                self
            ).exec(),
            NavigationItemPosition.BOTTOM
        )

        self.addSubInterface(self.settingInterface, FIF.SETTING, self.tr('设置'), position=NavigationItemPosition.BOTTOM)

        self.splashScreen.finish()
        self.themeListener = checkThemeChange(self)

        if not cfg.get_value(base64.b64decode("YXV0b191cGRhdGU=").decode("utf-8")):
            disclaimer(self)

    # main_window.py 只需修改关闭事件
    def closeEvent(self, e):
        if self.themeListener and self.themeListener.isRunning():
            self.themeListener.terminate()
            self.themeListener.deleteLater()
        super().closeEvent(e)

    def startGame(self):
        game = GameController(cfg.game_path, cfg.game_process_name, cfg.game_title_name, 'UnityWndClass')
        try:
            if game.start_game():
                InfoBar.success(
                    title=self.tr('启动成功(＾∀＾●)'),
                    content="",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self
                )
            else:
                InfoBar.warning(
                    title=self.tr('游戏路径配置错误(╥╯﹏╰╥)'),
                    content="请在“设置”-->“程序”中配置",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self
                )
        except Exception as e:
            InfoBar.warning(
                title=self.tr('启动失败'),
                content=str(e),
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )
            
