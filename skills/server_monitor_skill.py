import shutil
import psutil


def get_server_monitor_report() -> str:
    try:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage("/")

        disk_total_gb = disk.total / (1024 ** 3)
        disk_used_gb = disk.used / (1024 ** 3)
        disk_percent = (disk.used / disk.total) * 100 if disk.total else 0

        alerts = []
        if cpu >= 85:
            alerts.append("CPU偏高")
        if memory.percent >= 85:
            alerts.append("記憶體偏高")
        if disk_percent >= 90:
            alerts.append("磁碟偏高")

        overall = "目前伺服器運作正常，未偵測到明顯異常警報。" if not alerts else f"注意：{'、'.join(alerts)}。"

        return (
            "3. 伺服器狀況回報\n"
            f"{overall}\n"
            f"- CPU 使用率：{cpu:.1f}%\n"
            f"- 記憶體使用率：{memory.percent:.1f}%\n"
            f"- 磁碟使用率：{disk_percent:.1f}%（已用 {disk_used_gb:.1f} GB / 總計 {disk_total_gb:.1f} GB）"
        )
    except Exception as e:
        return f"3. 伺服器狀況回報\n取得資料失敗：{e}"
