# Author: hyperfield
# Email: inbox@quicknode.net
# Last update: September 6, 2024
# Project: YT Channel Downloader
# Description: This module contains the classes MainWindow, GetListThread
# and DownloadThread.
# License: MIT License

from urllib import error
import os
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot as Slot
from PyQt6 import QtGui, QtCore
from PyQt6.QtWidgets import QHeaderView
from PyQt6.QtWidgets import QApplication, QMainWindow, QDialog, QCheckBox, QMessageBox
from PyQt6.QtCore import QSemaphore
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

import assets.resources_rc as resources_rc    # Qt resources
from ui.ui_form import Ui_MainWindow
from ui.ui_about import Ui_aboutDialog
from classes.settings_manager import SettingsManager
from classes.enums import ColumnIndexes
from classes.get_list_thread import GetListThread
from classes.download_thread import DownloadThread
from classes.dialogs import CustomDialog
from classes.dialogs import YoutubeLoginDialog
from classes.login_prompt_dialog import LoginPromptDialog
from classes.delegates import CheckBoxDelegate
from classes.YTChannel import YTChannel
from classes.settings import SettingsDialog


class MainWindow(QMainWindow):
    """Main application window for the YouTube Channel Downloader.

    This class manages the primary UI components, their styling, signal
    connections, and interactions with other modules, such as Settings and
    YouTube login.

    Attributes:
        download_semaphore (QSemaphore): Controls the maximum number of
                                         simultaneous downloads.
        ui (Ui_MainWindow): Main UI layout.
        model (QStandardItemModel): Data model for displaying downloadable
                                    videos in a tree view.
        about_dialog (QDialog): Dialog window for the "About" information.
        settings_manager (SettingsManager): Manages user settings.
        user_settings (dict): Stores user-defined settings.
        selectAllCheckBox (QCheckBox): Checkbox for selecting all videos in
                                       the list.
        yt_chan_vids_titles_links (list): List of YouTube channel video title
                                          and link data.
        vid_dl_indexes (list): List of indexes of videos to download.
        dl_threads (list): List of download threads.
        dl_path_correspondences (dict): Map between video download paths and
                                        video data.
    """

    def __init__(self, parent=None):
        """Initializes the main window and its components.

        Args:
            parent (QWidget, optional): Parent widget, defaults to None.
        """
        super().__init__(parent)
        self.window_resize_needed = True
        self.init_styles()

        # Limit to 4 simultaneous downloads
        # TODO: Make this controllable in the Settings
        self.download_semaphore = QSemaphore(4)

        self.set_icon()
        self.center_on_screen()
        self.setup_ui()

        self.setup_about_dialog()
        self.init_download_structs()
        self.connect_signals()
        self.initialize_settings()
        self.setup_select_all_checkbox()
        self.initialize_youtube_login()

    def init_styles(self):
        """Applies global styles and element-specific styles for the main
        window."""
        self.setStyleSheet("""
            * { font-family: "Arial"; font-size: 12pt; }
            MainWindow {
                background-color: #f0f0f0;
                border-radius: 10px;
                font-family: Arial;
                font-size: 14pt;
            }
            QLabel {
                font-family: Arial;
                font-size: 14pt;
            }
            QLineEdit, QComboBox {
                border: 1px solid #A0A0A0;
                padding: 4px;
                border-radius: 4px;
            }
            QGroupBox {
                border: 1px solid #d3d3d3;
                padding: 10px;
                margin-top: 10px;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #0066ff;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #0000b3;
            }
            QTreeView {
                border: 1px solid #A0A0A0;
                padding: 4px;
                background-color: #FFFFFF;
            }
            QTreeView::item {
                padding: 5px;
            }
        """)

    def set_icon(self):
        """Sets the application icon."""
        icon_path = Path(__file__).resolve().parent.parent / "icon.png"
        self.setWindowIcon(QtGui.QIcon(str(icon_path)))

    def setup_ui(self):
        """Initializes main UI components and layout."""
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.model = QtGui.QStandardItemModel()
        self.setup_buttons()
        self.setup_tree_view_delegate()
        self.ui.actionDonate.triggered.connect(self.open_donate_url)

    def open_donate_url(self):
        """Opens the donation URL in the default web browser."""
        QDesktopServices.openUrl(QUrl("https://liberapay.com/hyperfield/donate"))

    def setup_button(self, button, callback):
        """Configures a button with the specified callback and font.

        Args:
            button (QPushButton): Button widget to set up.
            callback (function): Function to connect to button's clicked
            signal.
        """
        button.clicked.connect(callback)
        font = QFont("Arial", 12)
        font.setBold(True)
        button.setFont(font)

    def setup_buttons(self):
        """Sets up specific buttons used in the main window."""
        self.setup_button(self.ui.downloadSelectedVidsButton, self.dl_vids)
        self.setup_button(self.ui.getVidListButton, self.show_vid_list)

    def setup_tree_view_delegate(self):
        """Sets up a delegate for managing custom items in the tree view."""
        cb_delegate = CheckBoxDelegate()
        self.ui.treeView.setItemDelegateForColumn(ColumnIndexes.DOWNLOAD,
                                                  cb_delegate)

    def set_bold_font(self, widget, size):
        """Applies a bold font to a specific widget.

        Args:
            widget (QWidget): The widget to apply the font to.
            size (int): The font size to set.
        """
        font = QFont("Arial", size)
        font.setBold(True)
        widget.setFont(font)

    def setup_about_dialog(self):
        """Initializes and sets up the About dialog."""
        self.about_dialog = QDialog()
        self.about_ui = Ui_aboutDialog()
        self.about_ui.setupUi(self.about_dialog)

    def connect_signals(self):
        """Connects various UI signals to their respective slots."""
        self.ui.actionAbout.triggered.connect(self.show_about_dialog)
        self.ui.actionSettings.triggered.connect(self.showSettingsDialog)
        self.ui.actionExit.triggered.connect(self.exit)
        self.model.itemChanged.connect(self.update_download_button_state)
        self.update_download_button_state()

        for download_thread in self.dl_threads:
            download_thread.downloadProgressSignal.connect(
                self.handle_download_error)
            download_thread.downloadCompleteSignal.connect(
                self.show_download_complete)

    def handle_download_error(self, data):
        """Handles download error notifications from DownloadThread."""
        index = int(data["index"])
        error_type = data.get("error", "Unexpected error")

        if error_type == "Download error":
            self.show_download_error(index)
        elif error_type == "Network error":
            self.show_network_error(index)
        else:
            self.show_unexpected_error(index)

    def show_download_error(self, index):
        """Displays a dialog for download-specific errors."""
        QMessageBox.critical(self, "Download Error", f"An error occurred while downloading item {index}. Please check the URL and try again.")

    def show_network_error(self, index):
        """Displays a dialog for network-related errors."""
        QMessageBox.warning(self, "Network Error", f"Network issue encountered while downloading item {index}. Check your internet connection and try again.")

    def show_unexpected_error(self, index):
        """Displays a dialog for unexpected errors."""
        QMessageBox.warning(self, "Unexpected Error", f"An unexpected error occurred while downloading item {index}. Please try again later.")

    def show_download_complete(self, index):
        """Displays a dialog when a download completes successfully."""
        QMessageBox.information(self, "Download Complete", f"Download completed successfully for item {index}!")

    def initialize_settings(self):
        """Initializes user settings from the settings manager."""
        self.settings_manager = SettingsManager()
        self.user_settings = self.settings_manager.settings

    def setup_select_all_checkbox(self):
        """Sets up the Select All checkbox and adds it to the layout."""
        self.select_all_checkbox = QCheckBox("Select All", self)
        self.select_all_checkbox.setVisible(False)
        self.ui.verticalLayout.addWidget(self.select_all_checkbox)
        self.select_all_checkbox.stateChanged.connect(
            self.onSelectAllStateChanged)

    def init_download_structs(self):
        """Initializes download-related structures."""
        self.yt_chan_vids_titles_links = []
        self.vid_dl_indexes = []
        self.dl_threads = []
        self.dl_path_correspondences = {}

    def initialize_youtube_login(self):
        self.youtube_login_dialog = None
        self.ui.actionYoutube_login.triggered.connect(
            self.handle_youtube_login)
        self.check_youtube_login_status()

    def check_youtube_login_status(self):
        config_dir = self.settings_manager.get_config_directory()
        cookie_jar_path = Path(config_dir) / "youtube_cookies.txt"
        self.youtube_login_dialog = YoutubeLoginDialog(cookie_jar_path)
        self.update_youtube_login_menu()

    def show_youtube_login_dialog(self):
        if self.youtube_login_dialog and self.youtube_login_dialog.logged_in:
            self.youtube_login_dialog.logout()
            self.youtube_login_dialog = None  # Destroy the current instance
            self.ui.actionYoutube_login.setText("YouTube login")
        else:
            if self.youtube_login_dialog is None:
                config_dir = self.settings_manager.get_config_directory()
                cookie_jar_path = Path(config_dir) / "youtube_cookies.txt"
                self.youtube_login_dialog = YoutubeLoginDialog(cookie_jar_path)
                self.youtube_login_dialog.logged_in_signal.connect(
                    self.update_youtube_login_menu)

            self.youtube_login_dialog.show()

    def handle_youtube_login(self):
        if not self.youtube_login_dialog:
            config_dir = self.settings_manager.get_config_directory()
            cookie_jar_path = Path(config_dir) / "youtube_cookies.txt"
            self.youtube_login_dialog = YoutubeLoginDialog(cookie_jar_path)

        self.youtube_login_dialog.logged_in_signal.connect(
                self.update_youtube_login_menu)

        if not self.youtube_login_dialog.logged_in:
            user_settings = self.settings_manager.settings
            if not user_settings.get('dont_show_login_prompt'):
                login_prompt_dialog = LoginPromptDialog(self)
                if login_prompt_dialog.exec() == QDialog.DialogCode.Accepted:
                    self.show_youtube_login_dialog()
            else:
                self.show_youtube_login_dialog()
        else:
            # If already logged in, perform logout
            self.youtube_login_dialog.logout()
            self.ui.actionYoutube_login.setText("YouTube login")
            self.youtube_login_dialog = None

    def autoAdjustWindowSize(self):
        screen = QApplication.primaryScreen()
        screen_size = screen.size()
        full_screen_width = screen_size.width()
        max_height = round(screen_size.height() * 2 / 3)

        # Calculate total width
        total_width = 0
        for column in range(self.model.columnCount()):
            total_width += self.ui.treeView.columnWidth(column)
        total_width = min(total_width, full_screen_width)

        # Calculate total height of treeView contents
        content_height = self.ui.treeView.sizeHintForRow(0) \
            * self.model.rowCount()
        content_height += self.ui.treeView.header().height()
        total_height = min(content_height, max_height)

        # Resize window only if necessary
        if total_width >= self.width() or total_height != self.height():
            self.resize(round(total_width), total_height)

    def onSelectAllStateChanged(self, state):
        new_value = state == 2

        for row in range(self.model.rowCount()):
            item_title_index = self.model.index(row, 1)
            item_title = self.model.data(item_title_index)
            full_file_path = self.dl_path_correspondences[item_title]

            if full_file_path and \
               DownloadThread.is_download_complete(full_file_path):
                continue

            index = self.model.index(row, 0)
            self.model.setData(index, new_value, Qt.ItemDataRole.DisplayRole)

            # Update the Qt.CheckStateRole accordingly
            new_check_state = Qt.CheckState.Checked if new_value \
                else Qt.CheckState.Unchecked
            self.model.setData(index, new_check_state,
                               Qt.ItemDataRole.CheckStateRole)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        window_geometry = self.geometry()
        x_center = (screen_geometry.width() - window_geometry.width()) // 2
        y_center = (screen_geometry.height() - window_geometry.height()) // 2
        self.move(int(x_center), int(y_center))

    def reinit_model(self):
        self.model.clear()
        self.root_item = self.model.invisibleRootItem()
        self.model.setHorizontalHeaderLabels(
            ['Download?', 'Title', 'Link', 'Progress'])
        self.ui.treeView.setModel(self.model)

        # Set proportional widths
        header = self.ui.treeView.header()
        header.setSectionResizeMode(ColumnIndexes.DOWNLOAD,
                                    QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(ColumnIndexes.TITLE,
                                    QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(ColumnIndexes.LINK,
                                    QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(ColumnIndexes.PROGRESS,
                                    QHeaderView.ResizeMode.ResizeToContents)

        # Set relative stretch factors (adjust as needed)
        # To control each section individually
        header.setStretchLastSection(False)

        # Ensure "Progress" column stays narrow
        font_metrics = QFontMetrics(self.ui.treeView.font())
        max_text_width = font_metrics.horizontalAdvance("100%") + 10
        self.ui.treeView.setColumnWidth(3, max_text_width)

        self.select_all_checkbox.setVisible(False)

    def showSettingsDialog(self):
        settings_dialog = SettingsDialog()
        settings_dialog.exec()

    def show_about_dialog(self):
        self.about_ui.aboutLabel.setOpenExternalLinks(True)
        self.about_ui.aboutOkButton.clicked.connect(self.about_dialog.accept)
        self.about_dialog.exec()

    @Slot()
    def update_youtube_login_menu(self):
        if self.youtube_login_dialog and self.youtube_login_dialog.logged_in:
            self.ui.actionYoutube_login.setText("YouTube logout")
        else:
            self.ui.actionYoutube_login.setText("YouTube login")

    def update_download_button_state(self):
        self.ui.downloadSelectedVidsButton.setEnabled(False)
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:
                self.ui.downloadSelectedVidsButton.setEnabled(True)

    @Slot(str)
    def display_error_dialog(self, message):
        """
        Displays an error dialog with the given message and re-enables the
        'getVidListButton'.

        Parameters:
        message (str): The error message to be displayed.
        """
        dlg = CustomDialog("URL error", message)
        dlg.exec()
        self.ui.getVidListButton.setEnabled(True)

    def get_vid_list(self, channel_id, yt_channel):
        self.yt_chan_vids_titles_links.clear()
        self.yt_chan_vids_titles_links = \
            yt_channel.fetch_all_videos_in_channel(channel_id)

    def populate_window_list(self):
        self.reinit_model()
        for title_link in self.yt_chan_vids_titles_links:
            item_checkbox = QtGui.QStandardItem()
            item_checkbox.setCheckable(True)
            item_title = QtGui.QStandardItem(title_link[0])
            item_link = QtGui.QStandardItem(title_link[1])
            item_title_text = item_title.text()
            filename = DownloadThread.sanitize_filename(item_title_text)
            item = [item_checkbox, item_title,
                    item_link, QtGui.QStandardItem()]
            download_directory = self.user_settings.get(
                'download_directory', './')
            full_file_path = os.path.join(download_directory, filename)
            if DownloadThread.is_download_complete(full_file_path):
                item_checkbox.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable
                                       | QtCore.Qt.ItemFlag.ItemIsUserTristate)
                item_title.setForeground(QtGui.QBrush(QtGui.QColor('grey')))
                item_checkbox.setForeground(QtGui.QBrush(QtGui.QColor('grey')))
                item_link.setForeground(QtGui.QBrush(QtGui.QColor('grey')))
                item[3].setText("Complete")
            self.root_item.appendRow(item)
            self.dl_path_correspondences[item_title_text] = full_file_path
        self.ui.treeView.expandAll()
        self.ui.treeView.show()
        cb_delegate = CheckBoxDelegate()
        self.ui.treeView.setItemDelegateForColumn(ColumnIndexes.DOWNLOAD,
                                                  cb_delegate)
        self.ui.treeView.resizeColumnToContents(ColumnIndexes.DOWNLOAD)
        self.ui.treeView.resizeColumnToContents(ColumnIndexes.TITLE)
        self.ui.treeView.resizeColumnToContents(ColumnIndexes.LINK)
        self.ui.treeView.resizeColumnToContents(ColumnIndexes.PROGRESS)
        self.ui.treeView.setStyleSheet("""
        QTreeView::indicator:disabled {
            background-color: gray;
        }
        """)
        if self.model.rowCount() > 0:
            self.select_all_checkbox.setVisible(True)
            if self.window_resize_needed:
                self.autoAdjustWindowSize()
                self.window_resize_needed = False

    @Slot()
    def show_vid_list(self):
        self.window_resize_needed = True
        self.ui.getVidListButton.setEnabled(False)
        channel_url = self.ui.chanUrlEdit.text()
        yt_channel = YTChannel()
        yt_channel.showError.connect(self.display_error_dialog)
        channel_id = None

        if yt_channel.is_video_with_playlist_url(channel_url) or \
           yt_channel.is_playlist_url(channel_url):
            # Handle playlist URL
            self.get_list_thread = GetListThread(
                "playlist", yt_channel, channel_url)
            self.get_list_thread.finished.connect(self.handle_video_list)
            self.get_list_thread.finished.connect(
                self.enable_get_vid_list_button)
            self.get_list_thread.start()

        elif yt_channel.is_video_url(channel_url) or \
                yt_channel.is_short_video_url(channel_url):
            if yt_channel.is_short_video_url(channel_url):
                self.get_list_thread = GetListThread(
                    "short", yt_channel, channel_url)
            # Debug exception
            self.get_list_thread = GetListThread(channel_id, yt_channel,
                                                 channel_url)
            self.get_list_thread.finished.connect(self.handle_single_video)
            # Re-enable the button on completion
            self.get_list_thread.finished.connect(
                self.enable_get_vid_list_button)
            self.get_list_thread.start()

        else:
            # Handle as channel URL
            try:
                channel_id = yt_channel.get_channel_id(channel_url)
            except ValueError:
                self.display_error_dialog("Please check your URL")
                return
            except error.URLError:
                self.display_error_dialog("Please check your URL")
                return

            self.get_list_thread = GetListThread(channel_id, yt_channel)
            self.get_list_thread.finished.connect(self.handle_video_list)
            # Re-enable the button on completion
            self.get_list_thread.finished.connect(
                self.enable_get_vid_list_button)
            self.get_list_thread.start()

    @Slot(list)
    def handle_video_list(self, video_list):
        self.yt_chan_vids_titles_links = video_list
        self.populate_window_list()

    @Slot(list)
    def handle_single_video(self, video_list):
        self.yt_chan_vids_titles_links = video_list
        self.populate_window_list()

    @Slot()
    def enable_get_vid_list_button(self):
        self.ui.getVidListButton.setEnabled(True)

    @Slot()
    def dl_vids(self):
        # get all the indexes of the checked items
        self.vid_dl_indexes.clear()
        for row in range(self.model.rowCount()):
            item = self.model.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:  # Update here
                self.vid_dl_indexes.append(row)
        for index in self.vid_dl_indexes:
            progress_item = QtGui.QStandardItem()
            self.model.setItem(index, 3, progress_item)
            link = self.model.item(index, 2).text()
            title = self.model.item(index, 1).text()
            dl_thread = DownloadThread(link, index, title, self)
            dl_thread.downloadCompleteSignal.connect(self.populate_window_list)
            dl_thread.downloadProgressSignal.connect(self.update_progress)
            self.dl_threads.append(dl_thread)
            dl_thread.start()

    @Slot(dict)
    def update_progress(self, progress_data):
        file_index = int(progress_data["index"])
        progress = progress_data["progress"]
        progress_item = QtGui.QStandardItem(str(progress))
        self.model.setItem(int(file_index), 3, progress_item)
        self.ui.treeView.viewport().update()

    def exit(self):
        QApplication.quit()
