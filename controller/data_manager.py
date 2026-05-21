"""数据管理模块 - 测量记录存储、导出工作流"""

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QTableWidgetItem

from core.export import MeasurementExporter
from dialogs.export_dialog import ExportDialog
from dialogs.no_data_dialog import NoDataDialog

from datetime import datetime
import os


class DataManager(QObject):
    """管理测量表格数据和导出流程，表格通过依赖注入传入"""

    data_changed = pyqtSignal()

    def __init__(self, table_widget, parent=None):
        super().__init__(parent)
        self.table = table_widget
        self.auto_measurement_results = {}

    # ---- 表格记录 ----

    def add_record(self, m_type, value):
        """向表格追加一条测量记录"""
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem(m_type))
        self.table.setItem(row, 2, QTableWidgetItem(f"{value:.3f}"))
        self.table.setItem(row, 3, QTableWidgetItem("m"))

        now = datetime.now().strftime("%H:%M:%S")
        self.table.setItem(row, 4, QTableWidgetItem(now))

        self.data_changed.emit()

    def clear_records(self):
        """清空表格所有行"""
        self.table.setRowCount(0)
        self.data_changed.emit()

    # ---- 自动测量缓存 ----

    def set_auto_results(self, results_dict):
        """缓存自动测量结果，供导出时使用"""
        self.auto_measurement_results = results_dict

    def get_measurement_summary(self):
        """获取自动测量结果摘要的副本"""
        return dict(self.auto_measurement_results)

    # ---- 表格数据获取 ----

    def get_table_data(self):
        """获取表格中所有单元格文本的二维列表"""
        data = []
        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            data.append(row_data)
        return data

    # ---- 显示工具 ----

    @staticmethod
    def update_point_count(original, processed):
        """生成点云数量显示文本"""
        return f"原始：{original} | 处理后：{processed}"

    # ---- 导出工作流 ----

    def export_data(self, parent_widget):
        """完整导出流程：检查数据 -> 选择格式 -> 选择路径 -> 执行导出"""
        table_data = self.get_table_data()
        measurement_summary = self.get_measurement_summary()

        has_table_data = len(table_data) > 0
        has_summary = len(measurement_summary) > 0

        # 无任何数据时提示
        if not has_table_data and not has_summary:
            dialog = NoDataDialog(parent_widget)
            dialog.exec()
            return

        # 仅有摘要无明细时确认
        if not has_table_data and has_summary:
            reply = QMessageBox.question(
                parent_widget,
                "导出确认",
                "当前没有测量记录明细，\n是否仅导出测量结果摘要？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.No:
                return

        dialog = ExportDialog(parent_widget)
        if not dialog.exec():
            return

        export_format = dialog.get_format()

        file_filters = {
            "csv": "CSV 文件 (*.csv)",
            "xlsx": "Excel 文件 (*.xlsx)",
            "txt": "文本文件 (*.txt)",
        }

        default_name = f"测量报告_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        file_path, _ = QFileDialog.getSaveFileName(
            parent_widget,
            "保存测量报告",
            default_name,
            file_filters.get(export_format, "所有文件 (*.*)"),
        )

        if not file_path:
            return

        success, message = self._do_export(file_path, export_format, table_data, measurement_summary)

        if success:
            QMessageBox.information(parent_widget, "导出成功", f"测量数据已成功导出到：\n{file_path}")
            os.startfile(os.path.dirname(file_path))
        else:
            QMessageBox.critical(parent_widget, "导出失败", message)

    def _do_export(self, file_path, export_format, table_data, measurement_summary):
        """根据格式选择对应的导出方法"""
        if export_format == "csv":
            return MeasurementExporter.export_to_csv(file_path, table_data, measurement_summary)
        elif export_format == "xlsx":
            return MeasurementExporter.export_to_xlsx(file_path, table_data, measurement_summary)
        elif export_format == "txt":
            return MeasurementExporter.export_to_txt(file_path, table_data, measurement_summary)
        else:
            return False, "不支持的导出格式"
