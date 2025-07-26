import os
import re
import subprocess
from enum import Enum

import markdown
import requests
from packaging.version import parse
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from qfluentwidgets import InfoBar, InfoBarPosition

from module.config import cfg
from tasks.base.fastest_mirror import FastestMirror

from ..card.messagebox_custom import MessageBoxUpdate


class UpdateStatus(Enum):
    """更新状态枚举类，用于指示更新检查的结果状态。"""
    SUCCESS = 1
    UPDATE_AVAILABLE = 2
    FAILURE = 0


class UpdateThread(QThread):
    """负责后台检查更新的线程类。"""
    updateSignal = pyqtSignal(UpdateStatus)

    def __init__(self, timeout, flag):
        super().__init__()
        self.timeout = timeout  # 超时时间
        self.flag = flag  # 标志位，用于控制是否执行更新检查
        self.error_msg = ""  # 错误信息

    def remove_images_from_markdown(self, markdown_content):
        """从Markdown内容中移除图片标记。"""
        img_pattern = re.compile(r'!\[.*?\]\(.*?\)')
        return img_pattern.sub('', markdown_content)

    def fetch_latest_release_info(self):
        """获取最新的发布信息。"""
        response = requests.get(
            FastestMirror.get_github_api_mirror("moesnow", "March7thAssistant", not cfg.update_prerelease_enable),
            timeout=10,
            headers=cfg.useragent
        )
        response.raise_for_status()
        return response.json()[0] if cfg.update_prerelease_enable else response.json()

    def get_download_url_from_assets(self, assets):
        """从发布信息中获取下载URL。"""
        for asset in assets:
            if (cfg.update_full_enable and "full" in asset["browser_download_url"]) or \
               (not cfg.update_full_enable and "full" not in asset["browser_download_url"]):
                return asset["browser_download_url"]
        return None

    def run(self):
        """执行更新检查逻辑。"""
        try:
            if self.flag and not cfg.check_update:
                return

            data = self.fetch_latest_release_info()
            version = data["tag_name"]
            content = self.remove_images_from_markdown(data["body"])
            content = re.sub(r"\r\n\r\n首次.*?无法.*?！", "", content, flags=re.DOTALL)
            content = re.sub(r"\r\n\r\n\[.*?Mirror酱.*?CDK.*?下载\]\(https?://.*?mirrorchyan\.com[^\)]*\)", "", content, flags=re.IGNORECASE)
            if cfg.update_source == "GitHub":
                content = content + "\n\n若下载速度较慢，可尝试使用 Mirror酱（设置 → 关于 → 更新源） 高速下载"
            assert_url = self.get_download_url_from_assets(data["assets"])
            assert_name = assert_url.split("/")[-1]

            if assert_url is None:
                self.updateSignal.emit(UpdateStatus.SUCCESS)
                return
            if not cfg.update_prerelease_enable and cfg.update_full_enable and cfg.update_source == "MirrorChyan":
                if cfg.mirrorchyan_cdk == "":
                    self.error_msg = "未设置 Mirror酱 CDK"
                    self.updateSignal.emit(UpdateStatus.FAILURE)
                    return
                # 符合Mirror酱条件
                response = requests.get(
                    f"https://mirrorchyan.com/api/resources/March7thAssistant/latest?current_version={cfg.version}&cdk={cfg.mirrorchyan_cdk}",
                    timeout=10,
                    headers=cfg.useragent
                )
                if response.status_code == 200:
                    mirrorchyan_data = response.json()
                    if mirrorchyan_data["code"] == 0 and mirrorchyan_data["msg"] == "success":
                        version_name = mirrorchyan_data["data"]["version_name"]
                        url = mirrorchyan_data["data"]["url"]
                        if version_name == version:
                            assert_url = url
                else:
                    try:
                        mirrorchyan_data = response.json()
                        self.code = mirrorchyan_data["code"]
                        self.error_msg = mirrorchyan_data["msg"]

                        cdk_error_messages = {
                            7001: "Mirror酱 CDK 已过期",
                            7002: "Mirror酱 CDK 错误",
                            7003: "Mirror酱 CDK 今日下载次数已达上限",
                            7004: "Mirror酱 CDK 类型和待下载的资源不匹配",
                            7005: "Mirror酱 CDK 已被封禁"
                        }
                        if self.code in cdk_error_messages:
                            self.error_msg = cdk_error_messages[self.code]
                    except:
                        self.error_msg = "Mirror酱API请求失败"
                    self.updateSignal.emit(UpdateStatus.FAILURE)
                    return

            if parse(version.lstrip('v')) > parse(cfg.version.lstrip('v')):
                self.title = f"发现新版本：{cfg.version} ——> {version}\n更新日志 |･ω･)"
                self.content = "<style>a {color: #f18cb9; font-weight: bold;}</style>" + markdown.markdown(content)
                self.assert_url = assert_url
                self.assert_name = assert_name
                self.updateSignal.emit(UpdateStatus.UPDATE_AVAILABLE)
            else:
                self.updateSignal.emit(UpdateStatus.SUCCESS)
        except Exception as e:
            print(e)
            self.updateSignal.emit(UpdateStatus.FAILURE)


class UniverseUpdateThread(QThread):
    """负责后台检查 Auto_Simulated_Universe 更新的线程类。"""
    updateSignal = pyqtSignal(UpdateStatus)
    progressSignal = pyqtSignal(int)  # 进度信号
    statusSignal = pyqtSignal(str)    # 状态信息信号

    def __init__(self, timeout=10):
        super().__init__()
        self.timeout = timeout
        self.title = ""
        self.content = ""
        self.assert_url = ""
        self.assert_name = ""
        self.assert_sha256 = ""  # SHA256 哈希值
        self.error_msg = ""
        self._stop_requested = False  # 中断标志

    def stop(self):
        """请求停止线程"""
        self._stop_requested = True
        self.quit()
        self.wait(3000)  # 等待最多3秒

    def is_stopped(self):
        """检查是否请求停止"""
        return self._stop_requested

    def get_local_universe_version(self):
        """获取本地 Auto_Simulated_Universe 版本"""
        # 首先尝试从 version.ini 读取
        version_ini_file = os.path.join(str(cfg.universe_path), "version.ini")
        if os.path.exists(version_ini_file):
            try:
                import configparser
                config = configparser.ConfigParser()
                config.read(version_ini_file, encoding='utf-8')
                if 'Version' in config and 'current' in config['Version']:
                    version = config['Version']['current']
                    print(f"[DEBUG] 从 version.ini 读取版本: {version}")
                    return version
            except Exception as e:
                print(f"[DEBUG] 读取 version.ini 失败: {e}")
        
        # 兼容性：尝试从旧的 version.txt 读取
        version_txt_file = os.path.join(str(cfg.universe_path), "version.txt")
        if os.path.exists(version_txt_file):
            try:
                with open(version_txt_file, 'r', encoding='utf-8') as f:
                    version = f.read().strip()
                    print(f"[DEBUG] 从 version.txt 读取版本: {version}")
                    return version
            except Exception as e:
                print(f"[DEBUG] 读取 version.txt 失败: {e}")
        
        print("[DEBUG] 未找到版本文件，返回默认版本")
        return "v0.0.0"  # 默认版本，表示未安装或版本文件不存在

    def save_universe_version(self, version):
        """保存 Auto_Simulated_Universe 版本到本地（兼容性方法）"""
        version_ini_file = os.path.join(str(cfg.universe_path), "version.ini")
        try:
            os.makedirs(str(cfg.universe_path), exist_ok=True)
            
            # 写入到 version.ini
            import configparser
            config = configparser.ConfigParser()
            config['Version'] = {
                'current': version,
                'updated_at': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            with open(version_ini_file, 'w', encoding='utf-8') as f:
                config.write(f)
            
            print(f"[DEBUG] 版本信息已保存到 version.ini: {version}")
            
        except Exception as e:
            print(f"[DEBUG] 保存版本文件失败: {e}")
            self.error_msg = f"保存版本文件失败: {e}"

    def fetch_universe_release_info(self):
        """获取 Auto_Simulated_Universe 的最新发布信息"""
        try:
            # 使用项目中已有的镜像加速功能
            api_url = FastestMirror.get_github_api_mirror("CHNZYX", "Auto_Simulated_Universe")
            response = requests.get(
                api_url,
                timeout=self.timeout,
                headers=cfg.useragent
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"获取更新信息失败: {e}")

    def get_download_url_from_assets(self, assets):
        """从发布信息中获取下载URL，优先选择不带cpu的zip文件，同时获取SHA256值"""
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith('.zip') and 'cpu' not in name:
                # 从 digest 字段获取 SHA256 值（格式：sha256:xxxx）
                digest = asset.get("digest", "")
                sha256_hash = digest.replace("sha256:", "") if digest.startswith("sha256:") else None
                return asset["browser_download_url"], name, sha256_hash
        for asset in assets:
            name = asset.get("name", "")
            if name.endswith('.zip'):
                digest = asset.get("digest", "")
                sha256_hash = digest.replace("sha256:", "") if digest.startswith("sha256:") else None
                return asset["browser_download_url"], name, sha256_hash
        if assets:
            digest = assets[0].get("digest", "")
            sha256_hash = digest.replace("sha256:", "") if digest.startswith("sha256:") else None
            return assets[0]["browser_download_url"], assets[0].get("name", ""), sha256_hash
        return None, None, None

    def run(self):
        """执行 Auto_Simulated_Universe 更新检查逻辑"""
        try:
            # 检查配置是否启用自动检查更新
            if not cfg.get_value("universe_auto_check_update", True):
                return

            releases = self.fetch_universe_release_info()
            # releases: List[dict], 每个dict包含 tag_name, body, assets
            if not isinstance(releases, list):
                releases = [releases]

            local_version = self.get_local_universe_version()
            # 找到所有比本地版本新的版本，按tag_name降序排列
            new_releases = [r for r in releases if parse(r["tag_name"].lstrip('v')) > parse(local_version.lstrip('v'))]
            new_releases.sort(key=lambda r: parse(r["tag_name"].lstrip('v')), reverse=True)

            # 最新版本信息
            if new_releases:
                latest = new_releases[0]
                remote_version = latest["tag_name"]
                self.assert_url, self.assert_name, self.assert_sha256 = self.get_download_url_from_assets(latest["assets"])
                if self.assert_url is None:
                    self.error_msg = "没有找到可下载的文件"
                    self.updateSignal.emit(UpdateStatus.FAILURE)
                    return
                self.assert_url = FastestMirror.get_github_mirror(self.assert_url)
                self.title = f"模拟宇宙发现新版本：{local_version} ——> {remote_version}"

                # 拼接所有新版本的更新日志
                logs = []
                for release in new_releases:
                    tag = release["tag_name"]
                    body = release.get("body", "")
                    # 保持原始GitHub格式，移除图片但保留markdown
                    body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
                    logs.append(f"<h2>{tag}</h2>\n" + markdown.markdown(body))
                # 新到旧
                self.content = "<style>a {color: #f18cb9; font-weight: bold;}</style>" + "<hr>".join(logs)
                self.updateSignal.emit(UpdateStatus.UPDATE_AVAILABLE)
            else:
                self.updateSignal.emit(UpdateStatus.SUCCESS)
        except Exception as e:
            self.error_msg = str(e)
            self.updateSignal.emit(UpdateStatus.FAILURE)


def checkUpdate(self, timeout=5, flag=False):
    """检查更新，并根据更新状态显示不同的信息或执行更新操作。"""
    def handle_update(status):
        if status == UpdateStatus.UPDATE_AVAILABLE:
            # 显示更新对话框
            message_box = MessageBoxUpdate(
                self.update_thread.title,
                self.update_thread.content,
                self.window()
            )
            if message_box.exec():
                # 执行更新操作
                source_file = os.path.abspath("./March7th Updater.exe")
                assert_url = FastestMirror.get_github_mirror(self.update_thread.assert_url)
                # assert_url = self.update_thread.assert_url
                assert_name = self.update_thread.assert_name
                subprocess.Popen([source_file, assert_url, assert_name], creationflags=subprocess.DETACHED_PROCESS)
        elif status == UpdateStatus.SUCCESS:
            # 显示当前为最新版本的信息
            InfoBar.success(
                title=self.tr('当前是最新版本(＾∀＾●)'),
                content="",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1000,
                parent=self
            )
        else:
            # 显示检查更新失败的信息
            InfoBar.warning(
                title=self.tr('检测更新失败(╥╯﹏╰╥)'),
                content=self.update_thread.error_msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )

    self.update_thread = UpdateThread(timeout, flag)
    self.update_thread.updateSignal.connect(handle_update)
    self.update_thread.start()


def checkUniverseUpdate(self, timeout=10, flag=False):
    """检查 Auto_Simulated_Universe 更新"""
    def handle_universe_update(status):
        if status == UpdateStatus.UPDATE_AVAILABLE:
            # 导入对话框
            from ..card.universe_update_dialog import UniverseUpdateDialog
            from .universe_downloader import UniverseDownloadThread

            # 显示更新对话框
            dialog = UniverseUpdateDialog(
                self.universe_update_thread.title,
                self.universe_update_thread.content,
                self.window()
            )
            
            download_thread = None
            
            def start_download():
                """开始下载更新"""
                nonlocal download_thread
                try:
                    print("[DEBUG] 开始下载更新")  # 调试信息
                    # 获取远程版本
                    remote_version = self.universe_update_thread.title.split("——>")[-1].strip()
                    print(f"[DEBUG] 远程版本: {remote_version}")  # 调试信息
                    
                    # 创建下载线程
                    download_thread = UniverseDownloadThread(
                        self.universe_update_thread.assert_url,
                        self.universe_update_thread.assert_name,
                        remote_version,
                        self.universe_update_thread.assert_sha256  # 传递 SHA256
                    )
                    print(f"[DEBUG] 下载线程创建成功，URL: {self.universe_update_thread.assert_url}")  # 调试信息
                    
                    # 连接信号
                    download_thread.progressSignal.connect(dialog.update_progress)
                    download_thread.statusSignal.connect(dialog.update_status)
                    download_thread.completedSignal.connect(
                        lambda success, msg: dialog.update_completed(success, msg)
                    )
                    print("[DEBUG] 信号连接完成")  # 调试信息
                    
                    # 启动下载
                    download_thread.start()
                    print("[DEBUG] 下载线程已启动")  # 调试信息
                    
                except Exception as e:
                    print(f"[DEBUG] 启动下载失败: {e}")  # 调试信息
                    dialog.update_completed(False, f"启动下载失败：{str(e)}")
            
            def cancel_download():
                """取消下载"""
                if download_thread and download_thread.isRunning():
                    download_thread.stop()
                    download_thread.wait(5000)  # 等待最多5秒
                dialog.update_cancelled()
            
            # 连接对话框信号
            dialog.updateRequested.connect(start_download)
            dialog.cancelRequested.connect(cancel_download)
            
            # 显示对话框
            dialog.exec()
            
        elif status == UpdateStatus.SUCCESS:
            if not flag:  # 只在手动检查时显示"已是最新版本"
                InfoBar.success(
                    title=self.tr('模拟宇宙已是最新版本'),
                    content="",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=1000,
                    parent=self
                )
        else:
            # 显示检查更新失败的信息
            InfoBar.warning(
                title=self.tr('模拟宇宙更新检测失败'),
                content=self.universe_update_thread.error_msg,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )

    self.universe_update_thread = UniverseUpdateThread(timeout)
    self.universe_update_thread.updateSignal.connect(handle_universe_update)
    self.universe_update_thread.start()
