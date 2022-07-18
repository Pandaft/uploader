import os
import oss2
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


class CowUploader(threading.Thread):

    def __init__(self,
                 authorization: str,
                 remember_mev2: str,
                 upload_path: str,
                 folder_name: str = "",
                 title: str = "",
                 message: str = "",
                 valid_days: int = 7,
                 chunk_size: int = 2097152,
                 threads: int = 5):
        """
        实例化对象
        :param authorization: 用户 authorization
        :param remember_mev2: 用户 remember-mev2
        :param upload_path: 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        :param folder_name: 如果含有子文件夹，将所有文件上传至此文件夹中
        :param title: 传输标题（默认为空）
        :param message: 传输描述（默认为空）
        :param valid_days: 传输有效期（单位：天数，默认 7 天）
        :param chunk_size: 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        :param threads: 上传线程数（默认 5）
        """
        super(CowUploader, self).__init__()

        # 参数
        self.authorization = authorization
        self.remember_mev2 = remember_mev2
        self.upload_path = upload_path
        self.folder_name = folder_name
        self.title = title
        self.message = message
        self.valid_days = valid_days
        self.chunk_size = chunk_size
        self.threads = threads

        # 信息
        self.err = ""
        self.status = "work"
        self.file_dict = {}
        self.upload_info = {
            "complete": False
        }
        self.transfer_info = {}
        self.auth_headers = {
            "cookie": f"{self.remember_mev2}; cow-auth-token={self.authorization}",
            "authorization": self.authorization
        }

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
            if any([self.progress_bar_curr, self.progress_bar_total]):
                self.progress_bar_curr.clear()
                self.progress_bar_curr.disable = True
                self.progress_bar_curr.close()
            self.err = "已取消上传"
            return False
        return True

    def start_upload(self):
        """执行上传"""
        for step, func in [
            ("检查", self.check),
            ("获取专属域名", self.get_subdomain),
            ("初始化传输", self.init_transfer),
            ("初始化文件夹分片", self.init_folders),
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

        # 缺少 remember_mev2 或 authorization
        if not all([self.remember_mev2, self.authorization]):
            self.err = "错误：缺少 remember_mev2 或 authorization"
            return False

        # 待上传文件或目录
        if not os.path.exists(self.upload_path):
            self.err = "错误：待上传文件或目录不存在"
            return False

        return True

    def get_subdomain(self):
        """获取专属域名"""
        try:
            req_url = "https://cowtransfer.com/api/generic/v3/initial"
            resp = requests.get(url=req_url, headers=self.auth_headers)
            sub_domain = resp.json()["account"]["subDomain"]
            if not sub_domain:
                self.upload_info["url_prefix"] = f"https://cowtransfer.com/s/"
                return True
            self.upload_info["url_prefix"] = f"https://{sub_domain}.cowtransfer.com/s/"
            return True
        except Exception as exc:
            self.err = f"异常：{exc}"
            return False

    def init_transfer(self):
        """初始化传输"""
        try:
            req_url = "https://cowtransfer.com/core/api/transfer"
            req_json = {
                "name": self.title,  # 传输标题
                "message": self.message,  # 传输描述
                "validDays": self.valid_days,  # 传输有效期（单位：天）
                "enableDownload": True,  # 允许下载
                "enablePreview": True,  # 允许预览
                "enableSaveTo": True  # 允许转存
            }
            req_resp = requests.post(url=req_url, headers=self.auth_headers, json=req_json)
            resp_json = req_resp.json()
            if "code" in resp_json and resp_json["code"] == "0000":
                self.transfer_info.update(resp_json["data"])
                self.upload_info["transfer_url"] = self.upload_info["url_prefix"] + resp_json["data"]["uniqueUrl"]  # 传输链接
                self.upload_info["transfer_code"] = resp_json["data"]["downloadCode"]  # 传输取件码
                return True
            else:
                self.err = f"返回：{resp_json}"
        except Exception as exc:
            self.err = f"异常：{exc}"
            return False

    def init_folders(self):
        """初始文件夹结构"""

        # 判断待上传文件或目录是否存在
        if not os.path.exists(self.upload_path):
            self.err = "错误：待上传文件或目录不存在"
            return False

        # 判断上传目标类型
        if os.path.isfile(self.upload_path):
            # 单文件
            self.upload_info["mode"] = "single"
            self.file_dict["1"] = {
                "file_name": os.path.basename(self.upload_path),
                "file_format": os.path.basename(self.upload_path).split(".")[-1] if "." in os.path.basename(self.upload_path) else "unknow",
                "rel_path": "\\" + os.path.basename(self.upload_path),
                "abs_path": os.path.abspath(self.upload_path),
                "file_size": os.path.getsize(self.upload_path),
                "folder_id": "0",
                "uploaded": False,
                "uploaded_size": 0
            }
        else:
            # 目录，判断是否含有子文件夹
            self.upload_info["mode"] = "multiple"
            if any(map(lambda e: os.path.isdir(os.path.join(self.upload_path, e)), os.listdir(self.upload_path))):
                self.upload_info["mode"] = "folders"

            # 遍历获取所有待上传文件信息
            root_path = os.path.abspath(self.upload_path)
            for root, dirs, files in os.walk(self.upload_path):
                for file in files:
                    self.file_dict[str(len(self.file_dict) + 1)] = {
                        "file_name": os.path.basename(file),
                        "file_format": os.path.basename(file).split(".")[-1] if "." in os.path.basename(file) else "unknow",
                        "rel_path": os.path.abspath(os.path.join(root, file)).replace(root_path, ""),
                        "abs_path": os.path.abspath(os.path.join(root, file)),
                        "file_size": os.path.getsize(os.path.join(root, file)),
                        "folder_id": "0",
                        "uploaded": False,
                        "uploaded_size": 0
                    }

        # 含有子文件夹，需在云端创建并绑定处理
        if self.upload_info["mode"] == "folders":

            try:
                # 获取本地文件夹结构
                def get_children(parent_path: str):
                    """获取子文件夹"""
                    children_list = []
                    for child in os.listdir(parent_path):
                        if not os.path.isdir(os.path.join(parent_path, child)):
                            continue
                        children_list.append({
                            "title": child,
                            "children": get_children(str(os.path.join(parent_path, child)))
                        })
                    return children_list

                local_folder_structure = {
                    "folder": {
                        "title": self.folder_name or os.path.basename(os.path.split(self.upload_path)[0]),
                        "children": get_children(self.upload_path)
                    },
                    "handle_conflict": True
                }

                # 请求创建文件夹
                req_url = "https://cowtransfer.com/core/api/dam/folders/0/dfs"
                req_data = local_folder_structure
                req_resp = requests.post(url=req_url, headers=self.auth_headers, json=req_data)
                resp_json = req_resp.json()

                # 根文件夹ID
                self.upload_info["folder_id"] = resp_json["id"]

                # 获取文件夹ID
                folder_id_dict = {}

                def get_folder_id(parent_path: str, local_data: list, remote_data: list):
                    """获取文件夹ID"""
                    for local, remote in zip(local_data, remote_data):
                        folder_id_dict[f"{parent_path}\\{local['title']}"] = remote["id"]
                        if local["children"]:
                            get_folder_id(f"{parent_path}\\{local['title']}", local["children"], remote["children"])

                get_folder_id("", [local_folder_structure["folder"]], [resp_json])

                # 绑定文件夹ID
                for folder_path, folder_id in folder_id_dict.items():
                    for file_id, file_info in self.file_dict.items():
                        if folder_path.replace(f"\\{self.folder_name}", "") in file_info["abs_path"]:
                            self.file_dict[file_id]["folder_id"] = folder_id

            except Exception as exc:
                self.err = f"异常：{exc}"
                return False

        return True

    # 上传文件
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

        def close_progress_bar():
            """关闭进度条"""
            self.progress_bar_total.clear()
            self.progress_bar_total.disable = True
            self.progress_bar_total.close()
            self.progress_bar_curr.clear()
            self.progress_bar_curr.disable = True
            self.progress_bar_curr.close()
            return

        # 遍历上传
        for file_id, file_info in self.file_dict.items():
            if not self.action():
                return False
            log(f"开始上传：{file_info['rel_path']}……")
            self.progress_bar_curr.reset(file_info["file_size"])
            self.progress_bar_curr.set_description(f"当前 {file_info['rel_path']}")
            self.progress_bar_total.set_description(f"进度 {file_id}/{len(self.file_dict)}")

            # 获取凭证
            req_url = "https://cowtransfer.com/core/api/filems/front/upload/tokens"
            req_json = {
                "file_format": file_info["file_format"]
            }
            req_resp = requests.post(url=req_url, headers=self.auth_headers, json=req_json)
            resp_json = req_resp.json()

            # 初始化 bucket 对象
            bucket = oss2.Bucket(
                auth=oss2.StsAuth(
                    access_key_id=resp_json["access_key_id"],
                    access_key_secret=resp_json["access_key_secret"],
                    security_token=resp_json["security_token"]
                ),
                endpoint=resp_json["endpoint"],
                bucket_name=resp_json["bucket_name"]
            )

            # 上传分片
            def upload_part(part_num, part_data):
                """上传分片"""
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

            # 提交上传
            upl_path = resp_json["object_name"]
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
            bucket.complete_multipart_upload(upl_path, upload_id, parts)

            # 绑定文件
            bind_url = "https://cowtransfer.com/core/api/dam/asset/files"
            bind_data = {
                "folder_id": file_info["folder_id"],
                "file_md5": "",
                "file_sha1": "",
                "second_transmission": False,
                "file_info": {
                    "origin_url": f"{resp_json['host']}/{resp_json['object_name']}",
                    "size": file_info["file_size"],
                    "title": file_info["file_name"]
                }
            }
            resp = requests.post(url=bind_url, headers=self.auth_headers, json=bind_data)
            resp_json = resp.json()
            self.file_dict[file_id]["content_id"] = resp_json["content_id"]
            self.file_dict[file_id]["uploaded"] = True
            log(f"上传完成：{file_info['rel_path']}")

        close_progress_bar()
        return True

    def finish(self):
        """完成传输"""
        req_url = "https://cowtransfer.com/core/api/transfer/uploaded"
        if self.upload_info["mode"] in ["single", "multiple"]:
            req_json = {
                "files": [file["content_id"] for file in self.file_dict.values()],
                "folders": [],
                "guid": self.transfer_info["guid"]
            }
        elif self.upload_info["mode"] == "folders":
            req_json = {
                "files": [],
                "folders": [self.upload_info["folder_id"]],
                "guid": self.transfer_info["guid"]
            }
        else:
            self.err = "错误：未定义的上传模式"
            return False
        requests.post(url=req_url, headers=self.auth_headers, json=req_json)
        self.upload_info["complete"] = True
        return True


if __name__ == '__main__':
    upload_thread = CowUploader(
        authorization="___",  # 用户 authorization
        remember_mev2="___",  # 用户 remember-mev2
        upload_path="./test/",  # 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        folder_name="test",  # 如果含有子文件夹，将所有文件上传至此文件夹中
        title="",  # 传输标题（默认为空）
        message="",  # 传输描述（默认为空）
        valid_days=7,  # 传输有效期（单位：天数，默认 7 天）
        chunk_size=2097152,  # 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        threads=5  # 上传并发数（默认 5）
    )
    upload_thread.start()  # 开始上传
    # upload_thread.pause()  # 暂停上传
    # upload_thread.work()   # 继续上传
    # upload_thread.cancel()   # 取消上传
    upload_thread.join()  # 等待完成（阻塞直至完成）
    print(f"链接：{upload_thread.upload_info.get('transfer_url')}\n"
          f"口令：{upload_thread.upload_info.get('transfer_code')}")
