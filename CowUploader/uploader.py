import os
import json
import time
import base64
import hashlib
import requests
import threading
from tqdm import tqdm
from urllib import parse
from random import choices
from string import ascii_lowercase, digits
from concurrent.futures import ThreadPoolExecutor
from requests_toolbelt.multipart.encoder import MultipartEncoder

user_agent = "Mozilla/5.0 DevOps; Transfer/1.1 (KHTML, like Gecko) Chrome/97.0"


class CowUploader(threading.Thread):

    def __init__(self, authorization: str, remember_mev2: str, upload_path: str, valid_days: int = 7,
                 chunk_size: int = 2097152, message: str = "", threads: int = 5):
        """
        实例化对象
        :param authorization: 用户 authorization
        :param remember_mev2: 用户 remember-mev2
        :param upload_path: 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        :param valid_days: 传输有效期（单位：天数，默认 7 天）
        :param chunk_size: 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        :param threads: 上传线程数（默认 5）
        """
        super(CowUploader, self).__init__()
        self.authorization = authorization
        self.remember_mev2 = remember_mev2
        self.upload_path = upload_path
        self.valid_days = valid_days
        self.chunk_size = chunk_size
        self.message = message
        self.threads = threads

        self.err = ""
        self.upload_info = {}
        self.upload_files = {}
        self.progress_bar_curr = None
        self.progress_bar_total = None
        self.executor = None

    def run(self) -> str:
        return self.start_upload()

    def start_upload(self):
        """执行上传"""

        # 遍历文件
        if not self.get_upload_file_list():
            print("遍历待上传文件或目录时发生错误：", self.err)
            return False

        # 初始化上传
        if not self.init_upload():
            print("初始化上传时发生错误：", self.err)
            return False

        # 进度条
        self.progress_bar_total = tqdm(
            total=sum([f["file_size"] for f in self.upload_files.values()]),
            desc="进度", mininterval=0.1, unit="B", unit_scale=True, unit_divisor=1024
        )

        # 遍历上传
        self.progress_bar_curr = tqdm(
            total=1, desc=f"当前", mininterval=0.1,
            unit="B", unit_scale=True, unit_divisor=1024
        )
        for file_id, file_info in self.upload_files.items():
            self.progress_bar_curr.reset(file_info["file_size"])
            self.progress_bar_curr.set_description(f"当前 {file_info['rel_path']}")
            if not self.upload_file(file_id):
                print("上传失败：", self.err)
        self.progress_bar_curr.clear()
        self.progress_bar_curr.disable = True
        self.progress_bar_curr.close()

        # 完成上传
        if not self.complete():
            print("完成上传时出错：", self.err)

        self.progress_bar_total.clear()
        self.progress_bar_total.disable = True
        self.progress_bar_total.close()

        return f"链接：{self.upload_info['uniqueurl']}\n" \
               f"口令：{self.upload_info['tempDownloadCode']}"

    # 获取待上传文件列表
    def get_upload_file_list(self):
        """获取待上传文件列表"""
        if not os.path.exists(self.upload_path):
            self.err = "待上传文件或目录不存在"
            return False
        try:
            if os.path.isdir(self.upload_path):
                root_path = os.path.abspath(self.upload_path)
                for root, dirs, files in os.walk(self.upload_path):
                    for file in files:
                        self.upload_files[str(len(self.upload_files) + 1)] = {
                            "file_name": os.path.basename(file),
                            "rel_path": os.path.abspath(os.path.join(root, file)).replace(root_path, ""),
                            "abs_path": os.path.abspath(os.path.join(root, file)),
                            "file_size": os.path.getsize(os.path.join(root, file)),
                            "uploaded": False,
                            "uploaded_size": 0
                        }
            else:
                self.upload_files["1"] = {
                    "file_name": os.path.basename(self.upload_path),
                    "rel_path": "\\" + os.path.basename(self.upload_path),
                    "abs_path": os.path.abspath(self.upload_path),
                    "file_size": os.path.getsize(self.upload_path),
                    "uploaded": False,
                    "uploaded_size": 0
                }
        except Exception as exc:
            self.err = exc
            return False
        return True

    # 初始化上传
    def init_upload(self):
        """初始化上传"""

        def prepare_send():
            """准备发送"""
            req_url = "https://cowtransfer.com/api/transfer/v2/preparesend"
            req_data = {
                "name": "",
                "totalSize": str(sum(f["file_size"] for f in self.upload_files.values())),
                "message": self.message,
                "notifyEmail": "",
                "validDays": str(self.valid_days),
                "saveToMyCloud": "false",
                "downloadTimes": "-1",
                "smsReceivers": "",
                "emailReceivers": "",
                "enableShareToOthers": "true",
                "language": "cn",
                "enableDownload": "true",
                "enablePreview": "true"
            }
            try:
                req_resp = self.new_multipart_request(req_url, req_data)
                resp_json = req_resp.json()
                if resp_json.get("error") is not None:
                    if not resp_json.get("error"):
                        self.upload_info.update(resp_json)
                        return True
                    else:
                        self.err = resp_json.get("error_message")
                        return False
                else:
                    self.err = f"preparesend error: {resp_json}"
                    return False
            except Exception as exc:
                self.err = f"preparesend failed: {exc}"
                return False

        if not prepare_send():
            return False

        return True

    # 上传文件
    def upload_file(self, file_id):
        """上传文件"""

        self.progress_bar_total.set_description(f"进度 {file_id}/{len(self.upload_files)}")

        file_info = self.upload_files[file_id]
        relative_path = file_info["rel_path"].replace("\\", "/")
        relative_path = relative_path[1:] if os.path.split(relative_path)[0] == "/" else relative_path
        relative_path_quote = parse.quote(relative_path).replace("/", "%2F")

        # Before upload
        req_url = "https://cowtransfer.com/api/transfer/v2/beforeupload"
        req_data = {
            "type": "",
            "fileId": "",
            "fileName": relative_path_quote,
            "originalName": relative_path,
            "fileSize": str(file_info["file_size"]),
            "transferGuid": self.upload_info.get("transferguid"),
            "storagePrefix": self.upload_info.get("prefix"),
            "unfinishPath": "",
        }
        try:
            req_resp = self.new_multipart_request(req_url, req_data)
            resp_json = req_resp.json()
            file_guid = resp_json["fileGuid"]
            folder_guid = resp_json["folderGuid"]
            self.upload_info.update(resp_json)
            self.upload_info.update(resp_json)
        except Exception as exc:
            self.err = f"beforeupload failed: {exc}"
            return False

        # Get upload id
        path = f"{self.upload_info.get('prefix')}/{self.upload_info.get('transferguid')}/{relative_path_quote}"
        path_b64 = base64.b64encode(path.encode()).decode()
        req_url = f"https://upload.qiniup.com/buckets/cftransfer/objects/{path_b64}/uploads"
        req_data = {
            "transferGuid": self.upload_info.get("transferguid"),
            "storagePrefix": self.upload_info.get("prefix"),
        }
        try:
            req_resp = self.new_request("POST", req_url, req_data)
            resp_json = req_resp.json()
            upload_id = resp_json["uploadId"]
        except Exception as exc:
            self.err = f"Get upload id failed: {exc}"
            return False

        # Upload_chunk
        def upload_chunk(part_num, put_bytes):
            while True:
                put_url = f"https://upload.qiniup.com/buckets/cftransfer/objects" \
                          f"/{path_b64}/uploads/{upload_id}/{part_num}"
                put_resp = self.new_request("PUT", put_url, chunk_bytes)
                put_result = put_resp.json()

                # 校验（MD5）
                if put_result["md5"] == hashlib.md5(put_bytes).hexdigest():
                    self.progress_bar_total.update(len(put_bytes))
                    self.progress_bar_curr.update(len(put_bytes))
                    part_list.append({"etag": put_result["etag"], "partNumber": part_num})
                    return True

        # Add task
        chunk_id, task_list, part_list = 0, [], []
        self.executor = ThreadPoolExecutor(max_workers=self.threads)
        with open(file_info["abs_path"], "rb") as f:  # 流式上传
            while True:
                chunk_id += 1
                chunk_bytes = f.read(self.chunk_size)
                if len(chunk_bytes) != 0:
                    task_list.append(self.executor.submit(upload_chunk, chunk_id, chunk_bytes))
                    while [task.done() for task in task_list].count(False) > self.threads * 2:
                        time.sleep(0.1)
                    continue
                self.executor.shutdown()
                break

        # Merge
        req_url = f"https://upload.qiniup.com/buckets/cftransfer/objects/{path_b64}/uploads/{upload_id}"
        req_data = {
            "parts": sorted(part_list, key=lambda i: i["partNumber"]),
            "fname": file_info["file_name"]
        }
        req_resp = self.new_request("POST", req_url, json.dumps(req_data))
        resp_json = req_resp.json()

        # Finish
        rqe_url = "https://cowtransfer.com/api/transfer/v2/uploaded"
        req_data = {
            "hash": resp_json.get("hash"),
            "fileGuid": file_guid,
            "transferGuid": self.upload_info.get("transferguid"),
            "folderGuid": folder_guid
        }
        req_resp = self.new_multipart_request(rqe_url, req_data)
        if req_resp.json():
            return True
        else:
            self.err = f"uploaded fail: {req_resp.text}"
            return False

    # 完成上传
    def complete(self):
        """完成上传"""
        req_url = "https://cowtransfer.com/api/transfer/v2/complete"
        req_data = {
            "transferGuid": self.upload_info.get("transferguid"),
            "fileId": ""
        }
        req_resp = self.new_multipart_request(req_url, req_data)
        resp_json = req_resp.json()
        self.upload_info.update(resp_json)
        return True

    def new_request(self, method, url, data):
        headers = {
            "Authorization": "UpToken " + self.upload_info.get("uptoken"),
            "Referer": "https://cowtransfer.com/",
            "User-Agent": "Mozilla/5.0 DevOps; Transfer/1.1 (KHTML, like Gecko) Chrome/97.0",
            "Origin": "https://cowtransfer.com/"
        }
        headers["Cookie"] = f"{headers.get('cookie', '')}cf-cs-k-20181214={time.time_ns()};"
        return requests.request(method=method, url=url, data=data, headers=headers)

    def new_multipart_request(self, url, data):
        multipart = MultipartEncoder(
            fields=data,
            boundary="----WebKitFormBoundary" + "".join(choices(ascii_lowercase + digits, k=32))
        )
        headers = {
            "Content-Type": multipart.content_type,
            "cookie": f"{self.remember_mev2}; cow-auth-token={self.authorization}",
            "authorization": self.authorization
        }
        return requests.post(url, headers=headers, data=multipart)


if __name__ == '__main__':
    upload_thread = CowUploader(
        authorization="___",    # 用户 authorization
        remember_mev2="___",    # 用户 remember-mev2
        upload_path="./test/",  # 待上传文件或目录路径，如果是目录将上传该目录里的所有文件
        valid_days=7,           # 传输有效期（单位：天数，默认 7 天）
        chunk_size=2097152,     # 分块大小（单位：字节，默认 2097152 字节，即 2 MB）
        threads=5               # 上传线程数（默认 5）
    )
    upload_thread.start()  # 开始上传
    upload_thread.join()   # 等待完成
    if upload_thread.upload_info.get("complete", False):  # 判断结果
        print(f"链接：{upload_thread.upload_info.get('uniqueurl')}\n"
              f"口令：{upload_thread.upload_info.get('tempDownloadCode')}")
    else:
        print("上传失败")
