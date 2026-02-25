#!/home/jian/文档/code/.venv/bin/python
import os
import sys
import requests
import re
import time
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QTextEdit, QProgressBar,
                             QCheckBox, QGroupBox, QFileDialog, QMessageBox, QFrame,
                             QTabWidget, QListWidget, QListWidgetItem, QSplitter)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor, QLinearGradient, QPainter, QIcon
from PyQt5.QtCore import QRect, QSize

class DownloadThread(QThread):
    """下载线程"""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    log_updated = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    
    def __init__(self, bvid, download_video=False, save_danmaku=False, download_audio=False, output_dir='.'):
        super().__init__()
        self.bvid = bvid
        self.download_video = download_video
        self.save_danmaku = save_danmaku
        self.download_audio = download_audio
        self.output_dir = output_dir
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com/'
        })
    
    def run(self):
        try:
            self.log_updated.emit("🚀 开始处理下载任务...")
            self.status_updated.emit("正在获取视频信息...")
            
            video_info = self.get_video_info(self.bvid)
            
            if not video_info:
                self.log_updated.emit("❌ 获取视频信息失败")
                self.finished_signal.emit({'success': False, 'error': '获取视频信息失败'})
                return
            
            result = {
                'success': True,
                'video_info': video_info,
                'downloaded_files': []
            }
            
            self.log_updated.emit(f"✅ 成功获取视频信息: {video_info['title']}")
            
            # 处理多P视频
            pages = video_info['pages']
            for i, page in enumerate(pages):
                self.status_updated.emit(f"正在处理分P {i+1}/{len(pages)}")
                self.log_updated.emit(f"📦 处理分P {page['page']}: {page['part']}")
                cid = page['cid']
                
                # 获取弹幕
                if self.save_danmaku:
                    self.status_updated.emit("正在获取弹幕...")
                    self.log_updated.emit("📝 获取弹幕数据中...")
                    danmaku_list = self.get_danmaku(cid)
                    safe_title = self.sanitize_filename(video_info['title'])
                    safe_part = self.sanitize_filename(page['part'])
                    danmaku_filename = os.path.join(self.output_dir, f"{safe_title}_p{page['page']}_{safe_part}_danmaku.txt")
                    
                    if self.save_danmaku_to_file(danmaku_list, danmaku_filename):
                        result['downloaded_files'].append(danmaku_filename)
                        self.log_updated.emit(f"✅ 弹幕已保存: {os.path.basename(danmaku_filename)} ({len(danmaku_list)}条)")
                    else:
                        self.log_updated.emit("❌ 弹幕保存失败")
                
                # 下载视频
                if self.download_video:
                    self.status_updated.emit("正在获取视频地址...")
                    self.log_updated.emit("🔗 获取视频地址中...")
                    video_url = self.get_video_url(self.bvid, cid)
                    
                    if video_url:
                        safe_title = self.sanitize_filename(video_info['title'])
                        safe_part = self.sanitize_filename(page['part'])
                        video_filename = os.path.join(self.output_dir, f"{safe_title}_p{page['page']}_{safe_part}.mp4")
                        
                        self.status_updated.emit("开始下载视频...")
                        self.log_updated.emit(f"⬇️ 开始下载视频: {os.path.basename(video_filename)}")
                        
                        if self.download_video_file(video_url, video_filename):
                            result['downloaded_files'].append(video_filename)
                            self.log_updated.emit(f"✅ 视频下载完成: {os.path.basename(video_filename)}")
                            
                            # 如果同时选择了下载音频，从视频中提取音频
                            if self.download_audio:
                                self.extract_audio_from_video(video_filename, result)
                        else:
                            self.log_updated.emit("❌ 视频下载失败")
                    else:
                        self.log_updated.emit("❌ 无法获取视频地址")
                
                # 单独下载音频（不下载视频的情况下）
                elif self.download_audio:
                    if self.download_audio_only(self.bvid, cid, video_info, page, result):
                        self.log_updated.emit(f"✅ 音频下载完成")
                    else:
                        self.log_updated.emit("❌ 音频下载失败")
                
                time.sleep(1)
            
            self.log_updated.emit("🎉 所有任务完成！")
            self.finished_signal.emit(result)
            
        except Exception as e:
            self.log_updated.emit(f"💥 发生错误: {str(e)}")
            self.finished_signal.emit({'success': False, 'error': str(e)})
    
    def sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        return re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    def get_video_info(self, bvid):
        url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
        try:
            response = self.session.get(url)
            data = response.json()
            return data['data'] if data['code'] == 0 else None
        except:
            return None
    
    def get_video_url(self, bvid, cid, quality=80):
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': quality,
            'otype': 'json',
            'fourk': 1
        }
        url = "https://api.bilibili.com/x/player/playurl?" + urlencode(params)
        try:
            response = self.session.get(url)
            data = response.json()
            return data['data']['durl'][0]['url'] if data['code'] == 0 else None
        except:
            return None
    
    def get_danmaku(self, cid):
        url = f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
        try:
            response = self.session.get(url)
            danmaku_list = []
            pattern = r'<d p="([^"]*)">([^<]*)</d>'
            matches = re.findall(pattern, response.text)
            
            for match in matches:
                attrs = match[0].split(',')
                text = match[1]
                danmaku = {
                    'time': float(attrs[0]),
                    'text': text
                }
                danmaku_list.append(danmaku)
            return danmaku_list
        except:
            return []
    
    def save_danmaku_to_file(self, danmaku_list, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                for danmaku in danmaku_list:
                    f.write(f"{danmaku['time']}\t{danmaku['text']}\n")
            return True
        except:
            return False
    
    def download_video_file(self, video_url, filename):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        try:
            response = requests.get(video_url, headers=headers, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            self.progress_updated.emit(int(progress))
            
            return True
        except:
            return False

    def download_audio_only(self, bvid, cid, video_info, page, result):
        """单独下载音频"""
        try:
            self.status_updated.emit("正在获取音频流...")
            self.log_updated.emit("🎵 获取音频地址中...")
            
            # 方法1: 使用yt-dlp下载音频
            if self.download_with_ytdlp(bvid, video_info, page, result):
                return True
            
            # 方法2: 尝试直接获取音频URL
            audio_url = self.get_audio_url(bvid, cid)
            if audio_url:
                safe_title = self.sanitize_filename(video_info['title'])
                safe_part = self.sanitize_filename(page['part'])
                audio_filename = os.path.join(self.output_dir, f"{safe_title}_p{page['page']}_{safe_part}.mp3")
                
                self.status_updated.emit("开始下载音频...")
                self.log_updated.emit(f"⬇️ 开始下载音频: {os.path.basename(audio_filename)}")
                
                if self.download_audio_file(audio_url, audio_filename):
                    result['downloaded_files'].append(audio_filename)
                    return True
            
            self.log_updated.emit("❌ 所有音频下载方法都失败了")
            return False
            
        except Exception as e:
            self.log_updated.emit(f"❌ 音频下载错误: {str(e)}")
            return False
    
    def get_audio_url(self, bvid, cid):
        """获取音频流URL"""
        params = {
            'bvid': bvid,
            'cid': cid,
            'qn': 0,  # 音频质量
            'fnval': 16,  # 请求音频流
            'otype': 'json',
        }
        url = "https://api.bilibili.com/x/player/playurl?" + urlencode(params)
        try:
            response = self.session.get(url)
            data = response.json()
            if data['code'] == 0 and 'dash' in data['data']:
                # 提取音频流
                audio_streams = data['data']['dash']['audio']
                if audio_streams:
                    return audio_streams[0]['baseUrl']
            return None
        except:
            return None
    
    def download_audio_file(self, audio_url, filename):
        """下载音频文件"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.bilibili.com/'
        }
        try:
            response = requests.get(audio_url, headers=headers, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            self.progress_updated.emit(int(progress))
            
            return True
        except:
            return False
    
    def extract_audio_from_video(self, video_path, result):
        """从视频文件中提取音频"""
        try:
            self.status_updated.emit("正在提取音频...")
            self.log_updated.emit("🎵 从视频中提取音频...")
            
            audio_filename = os.path.splitext(video_path)[0] + '.mp3'
            
            # 使用系统ffmpeg命令
            try:
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-vn', '-acodec', 'mp3', '-ab', '192k',
                    '-y', audio_filename
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                
                if os.path.exists(audio_filename):
                    result['downloaded_files'].append(audio_filename)
                    self.log_updated.emit(f"✅ 音频提取完成: {os.path.basename(audio_filename)}")
                    return True
                    
            except subprocess.CalledProcessError as e:
                self.log_updated.emit(f"⚠️ FFmpeg提取失败: {e}")
            
            # 备选方案：使用python-ffmpeg（如果安装的话）
            try:
                import ffmpeg
                (
                    ffmpeg
                    .input(video_path)
                    .output(audio_filename, acodec='mp3', audio_bitrate='192k')
                    .overwrite_output()
                    .run(quiet=True, capture_stdout=True, capture_stderr=True)
                )
                
                if os.path.exists(audio_filename):
                    result['downloaded_files'].append(audio_filename)
                    self.log_updated.emit(f"✅ 音频提取完成: {os.path.basename(audio_filename)}")
                    return True
                    
            except ImportError:
                self.log_updated.emit("⚠️ 未安装ffmpeg-python，跳过此方法")
            except Exception as e:
                self.log_updated.emit(f"⚠️ python-ffmpeg提取失败: {e}")
            
            self.log_updated.emit("❌ 音频提取失败，请确保已安装FFmpeg")
            return False
            
        except Exception as e:
            self.log_updated.emit(f"❌ 音频提取错误: {str(e)}")
            return False
    
    def download_with_ytdlp(self, bvid, video_info, page, result):
        """使用yt-dlp下载音频（备选方案）"""
        try:
            self.log_updated.emit("🔄 尝试使用yt-dlp下载音频...")
            
            # 检查是否安装了yt-dlp
            try:
                import yt_dlp
            except ImportError:
                self.log_updated.emit("⚠️ 未安装yt-dlp，跳过此方法")
                return False
            
            safe_title = self.sanitize_filename(video_info['title'])
            safe_part = self.sanitize_filename(page['part'])
            output_template = os.path.join(self.output_dir, f"{safe_title}_p{page['page']}_{safe_part}")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'extractaudio': True,
                'audioformat': 'mp3',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                url = f"https://www.bilibili.com/video/{bvid}?p={page['page']}"
                info = ydl.extract_info(url, download=True)
                
                # 获取实际下载的文件名
                downloaded_file = ydl.prepare_filename(info)
                downloaded_file = downloaded_file.rsplit('.', 1)[0] + '.mp3'
                
                if os.path.exists(downloaded_file):
                    result['downloaded_files'].append(downloaded_file)
                    self.log_updated.emit(f"✅ yt-dlp音频下载完成: {os.path.basename(downloaded_file)}")
                    return True
            
            return False
            
        except Exception as e:
            self.log_updated.emit(f"❌ yt-dlp下载失败: {str(e)}")
            return False

class GradientHeader(QLabel):
    """渐变标题栏"""
    def __init__(self, text):
        super().__init__(text)
        self.setFixedHeight(80)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            GradientHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                font-size: 24px;
                font-weight: bold;
                border-bottom: 2px solid #5a6ae8;
            }
        """)

class ModernButton(QPushButton):
    """现代化按钮"""
    def __init__(self, text, primary=False):
        super().__init__(text)
        self.primary = primary
        self.setup_style()
    
    def setup_style(self):
        if self.primary:
            self.setStyleSheet("""
                ModernButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #667eea, stop:1 #764ba2);
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                }
                ModernButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #5a6ae8, stop:1 #6a4190);
                }
                ModernButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4a5ad8, stop:1 #5a3180);
                }
                ModernButton:disabled {
                    background: #cccccc;
                    color: #666666;
                }
            """)
        else:
            self.setStyleSheet("""
                ModernButton {
                    background: #f8f9fa;
                    color: #495057;
                    border: 2px solid #dee2e6;
                    padding: 10px 20px;
                    border-radius: 8px;
                    font-weight: bold;
                    font-size: 14px;
                }
                ModernButton:hover {
                    background: #e9ecef;
                    border-color: #adb5bd;
                }
                ModernButton:pressed {
                    background: #dee2e6;
                }
            """)

class ModernGroupBox(QGroupBox):
    """现代化分组框"""
    def __init__(self, title):
        super().__init__(title)
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernGroupBox {
                border: 2px solid #e9ecef;
                border-radius: 12px;
                margin-top: 1ex;
                padding-top: 15px;
                background: #ffffff;
                font-weight: bold;
                font-size: 14px;
                color: #495057;
            }
            ModernGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border-radius: 6px;
            }
        """)

class ModernProgressBar(QProgressBar):
    """现代化进度条"""
    def __init__(self):
        super().__init__()
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernProgressBar {
                border: 2px solid #e9ecef;
                border-radius: 10px;
                text-align: center;
                background: #f8f9fa;
                height: 20px;
            }
            ModernProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 8px;
            }
        """)

class ModernTextEdit(QTextEdit):
    """现代化文本编辑框"""
    def __init__(self):
        super().__init__()
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernTextEdit {
                border: 2px solid #e9ecef;
                border-radius: 8px;
                padding: 12px;
                background: #f8f9fa;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                selection-background-color: #667eea;
            }
        """)

class ModernLineEdit(QLineEdit):
    """现代化输入框"""
    def __init__(self, placeholder=""):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setup_style()
    
    def setup_style(self):
        self.setStyleSheet("""
            ModernLineEdit {
                border: 2px solid #e9ecef;
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                background: #ffffff;
                selection-background-color: #667eea;
            }
            ModernLineEdit:focus {
                border-color: #667eea;
                background: #fafbff;
            }
        """)

class BilibiliSpiderGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.download_thread = None
    
    def init_ui(self):
        self.setWindowTitle('B站视频下载器 - 现代化版 (支持音频下载)')
        self.setGeometry(100, 100, 1000, 700)
        
        # 设置应用样式
        self.setup_app_style()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题栏
        header = GradientHeader("🎬 B站视频下载器 - 支持音频下载")
        layout.addWidget(header)
        
        # 创建标签页
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 2px solid #e9ecef;
                border-radius: 8px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #f8f9fa;
                border: 2px solid #e9ecef;
                border-bottom: none;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 12px 24px;
                margin-right: 2px;
                font-weight: bold;
                color: #495057;
            }
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border-color: #667eea;
            }
            QTabBar::tab:hover:!selected {
                background: #e9ecef;
            }
        """)
        
        # 下载页面
        download_tab = QWidget()
        self.setup_download_tab(download_tab)
        tab_widget.addTab(download_tab, "🎯 视频下载")
        
        # 历史记录页面
        history_tab = QWidget()
        self.setup_history_tab(history_tab)
        tab_widget.addTab(history_tab, "📚 下载历史")
        
        layout.addWidget(tab_widget)
    
    def setup_app_style(self):
        """设置应用整体样式"""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
            QLabel {
                color: #495057;
                font-size: 14px;
            }
            QCheckBox {
                color: #495057;
                font-size: 14px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #adb5bd;
                border-radius: 4px;
                background: white;
            }
            QCheckBox::indicator:checked {
                background: #667eea;
                border-color: #667eea;
            }
        """)
    
    def setup_download_tab(self, tab):
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)
        
        # 输入区域
        input_group = ModernGroupBox("📥 视频信息")
        input_layout = QVBoxLayout(input_group)
        
        # BV号输入
        bv_layout = QHBoxLayout()
        bv_layout.addWidget(QLabel("🎯 BV号:"))
        self.bv_input = ModernLineEdit("请输入视频BV号，例如：BV1xx411c7mh")
        bv_layout.addWidget(self.bv_input)
        input_layout.addLayout(bv_layout)
        
        # 输出目录选择
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("📁 保存目录:"))
        self.dir_input = ModernLineEdit("选择文件保存目录")
        self.dir_input.setText(".")
        dir_layout.addWidget(self.dir_input)
        self.dir_button = ModernButton("浏览")
        self.dir_button.clicked.connect(self.select_directory)
        dir_layout.addWidget(self.dir_button)
        input_layout.addLayout(dir_layout)
        
        layout.addWidget(input_group)
        
        # 选项区域
        options_group = ModernGroupBox("⚙️ 下载选项")
        options_layout = QHBoxLayout(options_group)
        
        self.download_video_check = QCheckBox("下载视频")
        self.download_video_check.setChecked(True)
        options_layout.addWidget(self.download_video_check)
        
        self.download_danmaku_check = QCheckBox("下载弹幕")
        self.download_danmaku_check.setChecked(True)
        options_layout.addWidget(self.download_danmaku_check)
        
        # 添加音频下载选项
        self.download_audio_check = QCheckBox("下载音频")
        self.download_audio_check.setChecked(False)
        options_layout.addWidget(self.download_audio_check)
        
        options_layout.addStretch()
        layout.addWidget(options_group)
        
        # 添加选项说明
        option_note = QLabel("💡 说明: 下载音频时，如果同时下载视频会从视频中提取音频；如果只下载音频会直接下载音频流")
        option_note.setStyleSheet("""
            QLabel {
                background: #fff3cd;
                border: 2px solid #ffeaa7;
                border-radius: 8px;
                padding: 10px;
                color: #856404;
                font-size: 12px;
            }
        """)
        option_note.setWordWrap(True)
        layout.addWidget(option_note)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        self.start_button = ModernButton("🚀 开始下载", primary=True)
        self.start_button.clicked.connect(self.start_download)
        button_layout.addWidget(self.start_button)
        
        self.clear_button = ModernButton("🗑️ 清空")
        self.clear_button.clicked.connect(self.clear_input)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # 进度条
        self.progress_bar = ModernProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 状态显示
        self.status_label = QLabel("🟢 准备就绪")
        self.status_label.setStyleSheet("""
            QLabel {
                background: #e7f3ff;
                border: 2px solid #b3d9ff;
                border-radius: 8px;
                padding: 12px;
                color: #0066cc;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.status_label)
        
        # 信息显示区域
        info_group = ModernGroupBox("📊 视频信息和下载日志")
        info_layout = QVBoxLayout(info_group)
        self.info_display = ModernTextEdit()
        info_layout.addWidget(self.info_display)
        layout.addWidget(info_group)
    
    def setup_history_tab(self, tab):
        layout = QVBoxLayout(tab)
        
        # 历史记录列表
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                border: 2px solid #e9ecef;
                border-radius: 8px;
                background: #ffffff;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 12px;
                border-bottom: 1px solid #e9ecef;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
            }
            QListWidget::item:hover {
                background: #f8f9fa;
            }
        """)
        layout.addWidget(self.history_list)
        
        # 历史记录操作按钮
        history_buttons_layout = QHBoxLayout()
        self.clear_history_button = ModernButton("🗑️ 清空历史")
        self.clear_history_button.clicked.connect(self.clear_history)
        history_buttons_layout.addWidget(self.clear_history_button)
        
        self.open_folder_button = ModernButton("📂 打开文件夹")
        self.open_folder_button.clicked.connect(self.open_download_folder)
        history_buttons_layout.addWidget(self.open_folder_button)
        
        history_buttons_layout.addStretch()
        layout.addLayout(history_buttons_layout)
    
    def select_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if directory:
            self.dir_input.setText(directory)
    
    def start_download(self):
        bvid = self.bv_input.text().strip()
        if not bvid:
            self.show_message("警告", "请输入BV号", QMessageBox.Warning)
            return
        
        if not bvid.startswith('BV'):
            self.show_message("警告", "BV号格式不正确，应以BV开头", QMessageBox.Warning)
            return
        
        output_dir = self.dir_input.text().strip()
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except:
                self.show_message("警告", "无法创建输出目录", QMessageBox.Warning)
                return
        
        # 检查是否至少选择了一个下载选项
        if not any([
            self.download_video_check.isChecked(),
            self.download_danmaku_check.isChecked(),
            self.download_audio_check.isChecked()
        ]):
            self.show_message("警告", "请至少选择一个下载选项（视频、弹幕或音频）", QMessageBox.Warning)
            return
        
        # 禁用按钮，开始下载
        self.start_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.update_status("🟡 开始下载...")
        
        # 创建下载线程
        self.download_thread = DownloadThread(
            bvid=bvid,
            download_video=self.download_video_check.isChecked(),
            save_danmaku=self.download_danmaku_check.isChecked(),
            download_audio=self.download_audio_check.isChecked(),
            output_dir=output_dir
        )
        
        # 连接信号
        self.download_thread.progress_updated.connect(self.update_progress)
        self.download_thread.status_updated.connect(self.update_status)
        self.download_thread.log_updated.connect(self.update_log)
        self.download_thread.finished_signal.connect(self.download_finished)
        
        # 开始下载
        self.download_thread.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, message):
        self.status_label.setText(message)
    
    def update_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.info_display.append(f"[{timestamp}] {message}")
        # 自动滚动到底部
        self.info_display.verticalScrollBar().setValue(
            self.info_display.verticalScrollBar().maximum()
        )
    
    def download_finished(self, result):
        self.start_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        
        if result['success']:
            video_info = result['video_info']
            
            # 显示视频信息
            info_text = f"""
🎬 视频信息
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📺 标题: {video_info['title']}
👤 UP主: {video_info['owner']['name']}
📊 播放量: {video_info['stat']['view']}
💬 弹幕数: {video_info['stat']['danmaku']}
📅 发布时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(video_info['pubdate']))}

📦 下载完成文件:
"""
            for file_path in result['downloaded_files']:
                file_type = "🎵 音频" if file_path.endswith('.mp3') else "🎬 视频" if file_path.endswith('.mp4') else "📝 弹幕"
                info_text += f"   {file_type}: {os.path.basename(file_path)}\n"
                # 添加到历史记录
                self.add_to_history(file_path)
            
            self.info_display.setText(info_text)
            self.update_status("🟢 下载完成！")
            self.show_message("完成", "🎉 下载完成！", QMessageBox.Information)
        else:
            self.update_status("🔴 下载失败")
            self.show_message("错误", f"下载失败: {result['error']}", QMessageBox.Critical)
    
    def add_to_history(self, file_path):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        file_type = "🎵" if file_path.endswith('.mp3') else "🎬" if file_path.endswith('.mp4') else "📝"
        item_text = f"{timestamp} - {file_type} {os.path.basename(file_path)}"
        item = QListWidgetItem(item_text)
        item.setData(Qt.UserRole, file_path)
        self.history_list.addItem(item)
    
    def clear_history(self):
        self.history_list.clear()
    
    def open_download_folder(self):
        current_item = self.history_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.UserRole)
            folder_path = os.path.dirname(file_path)
            if os.path.exists(folder_path):
                if os.name == 'nt':  # Windows
                    os.startfile(folder_path)
                else:  # Linux/Mac
                    os.system(f'xdg-open "{folder_path}"')
    
    def clear_input(self):
        self.bv_input.clear()
        self.info_display.clear()
        self.update_status("🟢 准备就绪")
        self.progress_bar.setValue(0)
    
    def show_message(self, title, message, icon):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setIcon(icon)
        
        # 美化消息框
        msg.setStyleSheet("""
            QMessageBox {
                background: white;
                border: 2px solid #e9ecef;
                border-radius: 12px;
            }
            QMessageBox QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #5a6ae8, stop:1 #6a4190);
            }
        """)
        
        msg.exec_()

def main():
    # 设置环境变量（如果需要）
    if 'QT_QPA_PLATFORM' not in os.environ:
        os.environ['QT_QPA_PLATFORM'] = 'windows'
    
    app = QApplication(sys.argv)
    
    # 设置应用程序字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    window = BilibiliSpiderGUI()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()