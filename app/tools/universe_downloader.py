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
    
    def __init__(self, download_url, filename, version, sha256_hash=None, parent=None):
        super().__init__(parent)
        self.download_url = download_url
        self.filename = filename
        self.version = version
        self.sha256_hash = sha256_hash  # GitHub 提供的 SHA256 值
        self._stop_requested = False
        self.chunk_size = 8192  # 8KB chunks
        self.chunk_timeout = 30  # 30秒的chunk超时时间
        
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
                
            # 验证文件 SHA256（在解压前进行校验）
            if self.sha256_hash:
                self.statusSignal.emit("正在校验文件完整性...")
                print("[DEBUG] 开始 SHA256 校验")
                if not self.verify_file_sha256(download_path, self.sha256_hash):
                    self.completedSignal.emit(False, "文件 SHA256 校验失败：文件可能已损坏或下载不完整")
                    return
                print("[DEBUG] SHA256 校验通过")
            
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
            import time
            self.statusSignal.emit("正在连接服务器...")
            print(f"[DEBUG] 下载 URL: {url}")  # 调试信息

            # 获取文件大小
            try:
                response = requests.head(url, timeout=10, headers=self.headers, allow_redirects=True)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
            except Exception as e:
                print(f"[DEBUG] 获取文件大小失败: {e}")
                total_size = 0
            
            if total_size == 0:
                # 如果无法获取文件大小，使用流式下载
                self.statusSignal.emit("正在下载更新文件...")
                response = requests.get(url, stream=True, timeout=30, headers=self.headers)
                response.raise_for_status()
                
                downloaded_size = 0
                downloaded_bytes = 0  # 基于字节数触发进度更新
                last_update_time = time.time()
                
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if self._stop_requested:
                            return False
                        
                        if not chunk:
                            # 检测空数据，可能网络异常
                            current_time = time.time()
                            if current_time - last_update_time > self.chunk_timeout:
                                raise Exception("下载超时：接收数据为空")
                            continue
                            
                        f.write(chunk)
                        downloaded_size += len(chunk)  
                        downloaded_bytes += len(chunk)
                        last_update_time = time.time()
                        
                        # 基于字节数触发进度更新：每1MB更新一次
                        if downloaded_bytes >= 1024 * 1024:  # 1MB
                            downloaded_bytes = 0  # 重置计数器
                            # 模拟进度：基于时间控制，每5MB增加10%，最高90%
                            progress = min(90, int(downloaded_size / (5 * 1024 * 1024) * 10))
                            self.progressSignal.emit(progress)
                            # 更新状态
                            mb_size = downloaded_size / (1024 * 1024)
                            self.statusSignal.emit(f"已下载: {mb_size:.1f} MB")
                            
                self.progressSignal.emit(100)
                
                # 验证下载文件是否存在且有内容
                if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                    raise Exception("下载的文件为空或不存在")
                    
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
                    # 文件已完整下载，验证文件大小
                    if initial_downloaded_size == total_size:
                        self.progressSignal.emit(100)
                        return True
                    else:
                        # 文件大小不匹配，重新下载
                        os.remove(save_path)
                        initial_downloaded_size = 0 
            else:
                # 转换为MB显示
                mb_total = total_size / (1024 * 1024)
                self.statusSignal.emit(f"开始下载，文件大小: {mb_total:.1f} MB")
                    
            response = requests.get(url, headers=headers, stream=True, timeout=30)
            
            # 验证Range请求响应码
            if 'Range' in headers and response.status_code != 206:
                print(f"[DEBUG] 服务器不支持断点续传，响应码: {response.status_code}")
                # 服务器不支持断点续传，重新下载
                if os.path.exists(save_path):
                    os.remove(save_path)
                headers.pop('Range', None)
                initial_downloaded_size = 0
                response = requests.get(url, headers=headers, stream=True, timeout=30)
                
            response.raise_for_status()
            
            # 写入文件
            mode = 'ab' if initial_downloaded_size > 0 else 'wb'
            current_downloaded_size = initial_downloaded_size  # 当前总下载大小
            downloaded_bytes = 0  # 基于字节数的计数器
            last_update_time = time.time()
            
            with open(save_path, mode) as f:
                for chunk in response.iter_content(chunk_size=self.chunk_size):
                    if self._stop_requested:
                        return False
                        
                    if not chunk:
                        # 检测空数据和超时
                        current_time = time.time()
                        if current_time - last_update_time > self.chunk_timeout:
                            raise Exception("下载超时：网络连接异常")
                        continue
                        
                    f.write(chunk)
                    current_downloaded_size += len(chunk)
                    downloaded_bytes += len(chunk)
                    last_update_time = time.time()
                    
                    # 基于字节数触发进度更新：每512KB更新一次，避免过于频繁
                    if downloaded_bytes >= 512 * 1024:  # 512KB
                        downloaded_bytes = 0  # 重置计数器
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
                        
            # 下载完成，基本文件验证
            if not os.path.exists(save_path) or os.path.getsize(save_path) == 0:
                raise Exception("下载的文件为空或不存在")
                
            self.progressSignal.emit(100)
            return True
            
        except Exception as e:
            self.completedSignal.emit(False, f"下载失败：{str(e)}")
            return False
            
    def verify_file_sha256(self, file_path, expected_sha256):
        """验证文件的 SHA256 哈希值"""
        try:
            import hashlib
            print(f"[DEBUG] 开始校验文件 SHA256: {file_path}")
            print(f"[DEBUG] 期望 SHA256: {expected_sha256}")
            
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # 分块读取文件以节省内存
                for chunk in iter(lambda: f.read(self.chunk_size), b""):
                    sha256_hash.update(chunk)
                    
            calculated_sha256 = sha256_hash.hexdigest()
            print(f"[DEBUG] 计算的 SHA256: {calculated_sha256}")
            
            # 比较哈希值（不区分大小写）
            is_valid = calculated_sha256.lower() == expected_sha256.lower()
            print(f"[DEBUG] SHA256 校验结果: {'通过' if is_valid else '失败'}")
            
            return is_valid
            
        except Exception as e:
            print(f"[DEBUG] SHA256 校验过程中出错: {e}")
            return False
            
    def install_universe(self, zip_path):
        """安装 Auto_Simulated_Universe"""
        try:
            universe_path = str(cfg.universe_path) if cfg.universe_path else "./3rdparty/Auto_Simulated_Universe"
            
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
            universe_path = str(cfg.universe_path) if cfg.universe_path else "./3rdparty/Auto_Simulated_Universe"
            version_file = os.path.join(universe_path, "version.ini")
            print(f"[DEBUG] 保存版本信息到: {version_file}")
            
            # 确保目录存在
            os.makedirs(universe_path, exist_ok=True)
            
            # 写入版本信息到 version.ini
            with open(version_file, 'w', encoding='utf-8') as f:
                f.write("[Version]\n")
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
