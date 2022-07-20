import os
import oss2
import uuid
import time
import requests
import threading
from tqdm import tqdm
from oss2.models import PartInfo
from concurrent.futures import ThreadPoolExecutor

debug = False


def log(text: str) -> str:
    if debug:
        print(text)
    return text


class MuseUploader(threading.Thread):

    def __init__(self,
                 client_id: str,
                 client_key: str,
                 upload_path: str,
                 title: str = "untitled",
                 password: str = "",
                 valid_days: int = 7,
                 chunk_size: int = 2097152,
                 threads: int = 5):
        """
        实例化对象
        :param client_id: client_id
        :param client_key: client_key
        :param upload_path: 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        :param title: 分享链接的标题
        :param password: 分享链接的密码（4位数字，默认无密码）
        :param valid_days: 分享链接的有效期（默认 7 天，可选：7, 30, 365)
        :param chunk_size: 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        :param threads: 上传线程数（默认 5）
        """
        super(MuseUploader, self).__init__()

        # 参数
        self.client_id = client_id
        self.client_key = client_key
        self.upload_path = upload_path
        self.title = title
        self.password = password
        self.expire = valid_days
        self.chunk_size = chunk_size
        self.threads = threads

        # 信息
        self.err = ""
        self.status = "work"
        self.file_dict = {}
        self.auth_headers = {}
        self.upload_info = {
            "complete": False
        }
        self.transfer_info = {}

        # 对象
        self.executor = None
        self.progress_bar_curr = None
        self.progress_bar_total = None

    # 执行
    def run(self) -> bool:
        """执行"""
        return self.start_upload()

    # 继续
    def work(self):
        """继续"""
        self.status = "work"

    # 暂停
    def pause(self):
        """暂停"""
        self.status = "pause"

    # 取消
    def cancel(self):
        """取消"""
        self.status = "cancel"

    # 动作
    def action(self):
        """动作"""
        while self.status == "pause":
            time.sleep(1)
        if self.status == "cancel":
            self.close_progress_bar()
            self.err = "已取消上传"
            return False
        return True

    def close_progress_bar(self):
        """关闭进度条"""
        if self.progress_bar_total:
            self.progress_bar_total.clear()
            self.progress_bar_total.disable = True
            self.progress_bar_total.close()
        if self.progress_bar_curr:
            self.progress_bar_curr.clear()
            self.progress_bar_curr.disable = True
            self.progress_bar_curr.close()

    def start_upload(self):
        """执行上传"""
        for step, func in [
            ("检查", self.check),
            ("获取访问令牌", self.get_token),
            ("创建分享链接", self.create_share_url),
            ("获取上传令牌", self.get_upload_token),
            ("上传文件", self.upload_file),
            ("完成上传", self.finish),
        ]:
            log(f"{step}……")
            if not func():
                print(step, self.err)
                return False
            if not self.action():
                return False
        return True

    def check(self) -> bool:
        """检查"""

        # 缺少 client_id 或 client_key
        if not all([self.client_id, self.client_key]):
            self.err = "错误：缺少 client_id 或 client_key"
            return False

        # 待上传文件或目录
        if not os.path.exists(self.upload_path):
            self.err = "错误：待上传文件或目录不存在"
            return False
        self.get_file_info()
        total_size = sum(file["file_size"] for file in self.file_dict.values())
        if total_size > 10 * 1024 ** 3:
            self.err = f"错误：待上传文件总大小（{round(total_size / 1024 ** 3, 2)} GB）超过 10 GB"
            return False

        # 标题
        if not self.title:
            self.err = "错误：分享链接的标题不能为空"
            return False
        if len(self.title) > 64:
            self.err = "警告：分享链接的标题长度大于64位，超出部分将被丢弃"
            self.title = self.title[:64]  # official limited

        # 密码
        if self.password:
            if not self.password.isdigit():
                self.err = "错误：密码必须为数字"
                return False
            elif not len(self.password) == 4:
                self.err = "错误：密码长度必须为4位"
                return False

        # 有效期
        if self.expire not in [7, 30, 365]:
            self.err = "错误：有效期必须为 7, 30, 365 任一"

        return True

    def get_file_info(self) -> bool:
        """获取待上传文件信息"""

        # 判断上传目标类型
        if os.path.isfile(self.upload_path):
            # 文件
            abspath = os.path.abspath(self.upload_path).replace("\\", "/")
            filename = os.path.basename(abspath)
            self.file_dict[1] = {
                "abs_path": abspath,
                "upl_path": "\\" + filename,
                "file_name": filename,
                "uuid_name": str(uuid.uuid4()).replace("-", "") + "." + filename.split(".")[-1] if filename.split(".")[-1] != filename else "",
                "file_size": os.path.getsize(abspath),
                "uploaded_size": 0.0,
                "process": 0
            }
        else:
            # 目录
            for root, dirs, files in os.walk(self.upload_path):
                for name in files:
                    abspath = os.path.abspath(os.path.join(root, name)).replace("\\", "/")
                    self.file_dict[len(self.file_dict) + 1] = {
                        "abs_path": abspath,
                        "upl_path": abspath.replace(os.path.abspath(self.upload_path).replace("\\", "/"), "").strip("/"),
                        "file_name": name,
                        "uuid_name": str(uuid.uuid4()).replace("-", "") + "." + name.split(".")[-1] if name.split(".")[-1] != name else "",
                        "file_size": os.path.getsize(abspath),
                        "uploaded_size": 0.0,
                        "process": 0
                    }
        return True

    def get_token(self):
        """获取访问令牌"""
        try:
            req_url = "https://open-auth.tezign.com/open-api/oauth/get-token"
            resp = requests.post(url=req_url, json={"clientId": self.client_id, "clientKey": self.client_key})
            resp_json = resp.json()
            if resp_json.get("code") != "0":
                self.err = f"请求获取访问令牌失败：{resp_json.get('message', '未知原因')}"
                return False
            self.auth_headers = {
                "Access-token": resp_json["result"]["access_token"],
                "Token-type": resp_json["result"]["token_type"]
            }
            return True
        except Exception as exc:
            self.err = f"异常：{exc}"

    def create_share_url(self):
        """创建分享链接"""
        try:
            req_url = "https://open-auth.tezign.com/open-api/standard/simple/v1/muse/create"
            req_body = {
                "param": {
                    "pwd": self.password,
                    "title": self.title,
                    "expire": self.expire
                }
            }
            resp = requests.post(url=req_url, json=req_body, headers=self.auth_headers)
            resp_json = resp.json()
            if resp_json.get("code") != "0":
                self.err = f"请求创建分享链接失败：{resp_json.get('message', '未知原因')}"
                return False
            self.transfer_info["transfer_code"] = resp_json.get("result")
            self.upload_info["transfer_url"] = "https://musetransfer.com/s/" + resp_json.get("result")
            return True
        except Exception as exc:
            self.err = f"异常：{exc}"
            return False

    def get_upload_token(self):
        """获取上传令牌"""
        try:
            req_url = "https://open-auth.tezign.com/open-api/standard/simple/v1/muse/getUploadToken"
            req_body = {
                "param": self.transfer_info["transfer_code"]
            }
            resp = requests.post(url=req_url, json=req_body, headers=self.auth_headers)
            resp_json = resp.json()
            if resp_json.get("code") != "0":
                self.err = f"请求获取上传凭证失败：{resp_json.get('message', '未知原因')}"
                return False
            self.transfer_info["upload_token"] = resp_json.get("result")
            return True
        except Exception as exc:
            self.err = f"异常：{exc}"
            return False

    def upload_file(self):
        """上传文件"""

        # 进度条
        self.progress_bar_total = tqdm(
            total=sum([f["file_size"] for f in self.file_dict.values()]),
            desc="进度", mininterval=0.1, unit="B", unit_scale=True, unit_divisor=1024
        )
        self.progress_bar_curr = tqdm(
            total=1, desc=f"当前", mininterval=0.1,
            unit="B", unit_scale=True, unit_divisor=1024
        )

        # 初始化 bucket 对象
        bucket = oss2.Bucket(
            auth=oss2.StsAuth(
                access_key_id=self.transfer_info["upload_token"]["accessKeyId"],
                access_key_secret=self.transfer_info["upload_token"]["accessKeySecret"],
                security_token=self.transfer_info["upload_token"]["securityToken"]
            ),
            endpoint=self.transfer_info["upload_token"]["endpoint"],
            bucket_name=self.transfer_info["upload_token"]["bucket"]
        )

        # 上传切片
        def upload_part(part_num, part_data):
            """上传切片"""
            if not self.action():
                return False
            upload_result = bucket.upload_part(
                upl_path, upload_id, part_num, part_data
            )
            self.progress_bar_total.update(len(part_data))
            self.progress_bar_curr.update(len(part_data))
            self.file_dict[file_id]["uploaded_size"] += len(part_data)
            parts.append(PartInfo(part_num, upload_result.etag))
            return True

        # 上传文件
        for file_id, file_info in self.file_dict.items():
            if not self.action():
                return False
            log(f"开始上传：{file_info['upl_path']}……")
            self.progress_bar_curr.reset(file_info["file_size"])
            self.progress_bar_curr.set_description(f"当前 {file_info['upl_path']}")
            upl_path = self.transfer_info["upload_token"]["pathPrefix"] + "/" + file_info["uuid_name"]
            upload_id = bucket.init_multipart_upload(upl_path).upload_id
            parts = []
            chunk_id, task_list = 0, []
            self.executor = ThreadPoolExecutor(max_workers=self.threads)
            with open(file_info["abs_path"], "rb") as f:
                while True:
                    if not self.action():
                        return False
                    chunk_id += 1
                    chunk_bytes = f.read(self.chunk_size)
                    if len(chunk_bytes) != 0:
                        task_list.append(self.executor.submit(upload_part, chunk_id, chunk_bytes))
                        while [task.done() for task in task_list].count(False) > self.threads * 2:
                            time.sleep(0.1)
                        continue
                    self.executor.shutdown()
                    break
            complete_result = bucket.complete_multipart_upload(upl_path, upload_id, parts)

            # 绑定文件
            req_body = {
                "param": {
                    "code": self.transfer_info["transfer_code"],
                    "filePathList": [
                        {
                            "etag": complete_result.etag,
                            "fileName": file_info["upl_path"],
                            "path": upl_path
                        }
                    ],
                    "finish": 0
                }
            }
            req_url = "https://open-auth.tezign.com/open-api/standard/simple/v1/muse/bindFile"
            resp = requests.post(url=req_url, json=req_body, headers=self.auth_headers)
            resp_json = resp.json()
            if resp_json.get("code") != "0":
                self.err = f"上传文件 {file_info['upl_path']} 失败：{resp_json.get('message', '未知原因')}"
                self.close_progress_bar()
                return False
            log(f"上传完成：{file_info['upl_path']}")

        self.close_progress_bar()
        return True

    def finish(self):
        """完成传输"""
        try:
            req_url = "https://open-auth.tezign.com/open-api/standard/simple/v1/muse/finish"
            req_body = {
                "param": self.transfer_info["transfer_code"]
            }
            resp = requests.post(url=req_url, json=req_body, headers=self.auth_headers)
            resp_json = resp.json()
            if resp_json.get("code") != "0":
                self.err = f"请求完成传输失败：{resp_json.get('message', '未知原因')}"
                return False
            self.transfer_info["upload_token"] = resp_json.get("result")
            self.upload_info["complete"] = True
            return True
        except Exception as exc:
            self.err = f"异常：{exc}"
            return False


if __name__ == '__main__':
    upload_thread = MuseUploader(
        client_id="___",  # client_id
        client_key="___",  # client_key
        upload_path="./test/",  # 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        title="untitled",  # 分享链接的标题
        password="",  # 分享链接的密码（4位数字，默认无密码）
        valid_days=7,  # 分享链接的有效期（默认 7 天，可选：7, 30, 365)
        chunk_size=2097152,  # 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        threads=5,  # 上传线程数（默认 5）
    )
    upload_thread.start()  # 开始上传
    # upload_thread.pause()  # 暂停上传
    # upload_thread.work()   # 继续上传
    # upload_thread.cancel()   # 取消上传
    upload_thread.join()  # 等待完成（阻塞直至完成）
    print(f"链接：{upload_thread.upload_info.get('transfer_url')}")
