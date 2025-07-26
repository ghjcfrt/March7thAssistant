import os
import shutil
import zipfile

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from module.config import cfg
from tasks.base.fastest_mirror import FastestMirror


class UniverseDownloadThread(QThread):
    """负责下载和安装 Auto_Simulated_Universe 的线程类"""
    
    progressSignal = pyqtSignal(int)      # 下载进度信号
    statusSignal = pyqtSignal(str)        # 状态信息信号
    completedSignal = pyqtSignal(bool, str)  # 完成信号 (成功/失败, 消息)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Encoding": "identity",  # 防止返回 gzip 导致读取失败
        "Connection": "keep-alive",
    }
    
    def __init__(self, download_url, filename, version, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.filename = filename
        self.version = version
        self._stop_requested = False
        self.chunk_size = 8192  # 8KB chunks
        
    def stop(self):
        """请求停止下载"""
        self._stop_requested = True
        
    def run(self):
        """执行下载和安装"""
        try:
            self.statusSignal.emit("正在连接服务器...")
            self.progressSignal.emit(0)  # 初始进度
            
            # 创建临时下载目录
            temp_dir = os.path.join("temp", "universe_update")
            os.makedirs(temp_dir, exist_ok=True)
            
            download_path = os.path.join(temp_dir, self.filename)
            
            # 下载文件
            self.statusSignal.emit("正在下载更新文件...")
            if not self.download_file(self.download_url, download_path):
                return
                
            if self._stop_requested:
                self.completedSignal.emit(False, "下载已取消")
                return
                
            # 解压安装
            self.statusSignal.emit("正在解压文件...")
            self.progressSignal.emit(0)  # 重置进度条
            
            if not self.install_universe(download_path):
                return
                
            if self._stop_requested:
                self.completedSignal.emit(False, "安装已取消")
                return
                
            # 完成
            self.statusSignal.emit("更新完成！")
            self.progressSignal.emit(100)
            self.completedSignal.emit(True, "模拟宇宙更新完成")
            
        except Exception as e:
            self.completedSignal.emit(False, f"更新失败：{str(e)}")
            
    def download_file(self, url, save_path):
        """下载文件，支持进度显示和中断"""
        try:
            self.statusSignal.emit("正在连接服务器...")
            print(f"[DEBUG] 下载 URL: {url}")  # 调试信息

            # 获取文件大小
            try:
                response = requests.head(url, timeout=10, headers=self.headers, allow_redirects=True)
                total_size = int(response.headers.get('content-length', 0))
            except Exception:
                total_size = 0
            
            if total_size == 0:
                # 如果无法获取文件大小，使用流式下载
                self.statusSignal.emit("正在下载更新文件...")
                response = requests.get(url, stream=True, timeout=10, headers=self.headers)
                response.raise_for_status()
                
                downloaded_size = 0
                chunk_count = 0
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if self._stop_requested:
                            return False
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            chunk_count += 1
                            
                            # 无法获知总大小时，模拟进度增长，每处理20个chunk更新一次
                            if chunk_count % 20 == 0:
                                # 模拟进度：每5MB增加10%，最高100%
                                progress = min(100, int(downloaded_size / (5 * 1024 * 1024) * 10))
                                self.progressSignal.emit(progress)
                                # 更新状态
                                mb_size = downloaded_size / (1024 * 1024)
                                self.statusSignal.emit(f"已下载: {mb_size:.1f} MB")
                            
                self.progressSignal.emit(100)
                return True
            
            # 支持断点续传的下载
            initial_downloaded_size = 0
            headers = dict(self.headers)  # 创建headers副本

            # 检查是否有部分下载的文件
            if os.path.exists(save_path):
                initial_downloaded_size = os.path.getsize(save_path)
                if initial_downloaded_size < total_size:
                    headers['Range'] = f'bytes={initial_downloaded_size}-'
                    # 转换为MB显示
                    mb_downloaded = initial_downloaded_size / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    self.statusSignal.emit(f"断点续传，已下载 {mb_downloaded:.1f}/{mb_total:.1f} MB")
                    # 设置初始进度
                    initial_progress = int(initial_downloaded_size * 100 / total_size)
                    self.progressSignal.emit(initial_progress)
                else:
                    # 文件已完整下载
                    self.progressSignal.emit(100)
                    return True
            else:
                # 转换为MB显示
                mb_total = total_size / (1024 * 1024)
                self.statusSignal.emit(f"开始下载，文件大小: {mb_total:.1f} MB")
                    
            response = requests.get(url, headers=headers, stream=True, timeout=10)
            response.raise_for_status()
            
            # 写入文件
            mode = 'ab' if initial_downloaded_size > 0 else 'wb'
            current_downloaded_size = initial_downloaded_size  # 当前总下载大小
            
            with open(save_path, mode) as f:
                chunk_count = 0
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._stop_requested:
                        return False
                        
                    if chunk:
                        f.write(chunk)
                        current_downloaded_size += len(chunk)
                        chunk_count += 1
                        
                        # 每处理10个chunk更新一次进度，避免过于频繁的UI更新
                        if chunk_count % 10 == 0:
                            # 更新进度 (下载占100%)
                            progress = min(100, int(current_downloaded_size * 100 / total_size))
                            mb_downloaded = current_downloaded_size / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            print(f"[DEBUG] 下载进度: {progress}%, {mb_downloaded:.2f}/{mb_total:.2f} MB")  # 调试信息
                            self.progressSignal.emit(progress)
                            
                            # 更新状态信息
                            percent = current_downloaded_size * 100 / total_size
                            status_text = f"下载进度: {percent:.1f}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)"
                            print(f"[DEBUG] 状态更新: {status_text}")  # 调试信息
                            self.statusSignal.emit(status_text)
                        
            # 下载完成
            self.progressSignal.emit(100)
            return True
            
        except Exception as e:
            self.completedSignal.emit(False, f"下载失败：{str(e)}")
            return False
            
    def install_universe(self, zip_path):
        """安装 Auto_Simulated_Universe"""
        try:
            universe_path = cfg.universe_path
            
            # 确保目标目录存在
            self.progressSignal.emit(10)
            os.makedirs(universe_path, exist_ok=True)
            
            # 备份当前版本 (如果存在)
            self.progressSignal.emit(20)
            backup_path = "./bak"
            if os.path.exists(universe_path) and os.listdir(universe_path):
                backup_path = f"{universe_path}_backup"
                if os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                shutil.copytree(universe_path, backup_path)
                
            try:
                # 解压新版本
                self.progressSignal.emit(40)
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # 解压到临时目录
                    self.progressSignal.emit(50)
                    temp_extract_path = os.path.join("temp", "universe_extract")
                    
                    # 清理之前解压的临时目录（避免旧文件干扰）
                    if os.path.exists(temp_extract_path):
                        shutil.rmtree(temp_extract_path)
                    
                    # 解压整个压缩包内容
                    zip_ref.extractall(temp_extract_path)
                    
                    if self._stop_requested:
                        return False
                        
                    # 移动文件到目标目录
                    self.progressSignal.emit(70)
                    
                    # 清空目标目录
                    if os.path.exists(universe_path) and os.listdir(universe_path):
                        for item in os.listdir(universe_path):
                            item_path = os.path.join(universe_path, item)
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.remove(item_path)
                    
                    # 复制解压后的所有文件到目标目录
                    self.progressSignal.emit(85)
                    for item in os.listdir(temp_extract_path):
                        src = os.path.join(temp_extract_path, item)
                        dst = os.path.join(universe_path, item)
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
                            
                    # 清理临时解压目录
                    self.progressSignal.emit(95)
                    shutil.rmtree(temp_extract_path)
                        
                # 删除备份 (安装成功)
                if backup_path and os.path.exists(backup_path):
                    shutil.rmtree(backup_path)
                    
                # 保存版本信息
                self.save_version_info()
                
                # 清理临时文件
                # self.cleanup_temp_files(os.path.join("temp", "universe_update"))
                
                self.progressSignal.emit(100)
                return True
                
            except Exception as e:
                # 恢复备份
                if backup_path and os.path.exists(backup_path):
                    if os.path.exists(universe_path):
                        shutil.rmtree(universe_path)
                    shutil.move(backup_path, universe_path)
                raise e
                
        except Exception as e:
            self.completedSignal.emit(False, f"安装失败：{str(e)}")
            return False
            
    def save_version_info(self):
        """保存版本信息到 version.ini 文件"""
        try:
            version_file = os.path.join(str(cfg.universe_path), "version.ini")
            print(f"[DEBUG] 保存版本信息到: {version_file}")
            
            # 确保目录存在
            os.makedirs(str(cfg.universe_path), exist_ok=True)
            
            # 写入版本信息到 version.ini
            with open(version_file, 'w', encoding='utf-8') as f:
                f.write(f"[Version]\n")
                f.write(f"current={self.version}\n")
                f.write(f"updated_at={__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            
            print(f"[DEBUG] 版本信息已保存: {self.version}")
            
        except Exception as e:
            print(f"[DEBUG] 版本文件保存失败: {e}")
            pass  # 版本文件保存失败不影响主流程
            
    def cleanup_temp_files(self, temp_dir):
        """清理临时文件"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception:
            print("临时文件清理失败")
            pass  # 清理失败不影响主流程
