"""
腾讯云 - 混元生图 API Python 工具

支持：
- 混元生图 3.0（异步）：文生图 / 图生图（最多 3 张参考图）
  - 提交任务：SubmitTextToImageJob
  - 查询任务：QueryTextToImageJob
- 混元生图 2.0 极速版（同步）：TextToImageRapid，作为快速备选

参考文档：
- 提交混元生图 3.0 任务：https://cloud.tencent.com/document/api/1668/124632
- 查询混元生图 3.0 任务：https://cloud.tencent.com/document/api/1668/124633
- 混元生图 2.0（极速版）：https://cloud.tencent.com/document/api/1668/120720

前置条件：
- pip install -U tencentcloud-sdk-python
- 环境变量：
  - TENCENTCLOUD_SECRET_ID
  - TENCENTCLOUD_SECRET_KEY
"""

import os
import time
import base64
import mimetypes
import urllib.request
from pathlib import Path
from typing import Optional, List, Union

try:
    from tencentcloud.common import credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    from tencentcloud.aiart.v20221229 import aiart_client, models
except ImportError:
    print("请安装腾讯云 SDK: pip install -U tencentcloud-sdk-python")
    raise


class TencentHunyuanImage:
    """腾讯云混元生图封装（3.0 异步 + 2.0 极速版同步）"""

    DEFAULT_REGION = "ap-guangzhou"
    DEFAULT_ENDPOINT = "aiart.tencentcloudapi.com"

    # 任务状态码
    JOB_STATUS_WAITING = "1"
    JOB_STATUS_RUNNING = "2"
    JOB_STATUS_FAILED = "4"
    JOB_STATUS_DONE = "5"

    def __init__(
        self,
        secret_id: str = None,
        secret_key: str = None,
        region: str = None,
        endpoint: str = None,
    ):
        """
        初始化混元生图客户端

        Args:
            secret_id: 腾讯云 SecretId，默认从环境变量 TENCENTCLOUD_SECRET_ID 获取
            secret_key: 腾讯云 SecretKey，默认从环境变量 TENCENTCLOUD_SECRET_KEY 获取
            region: 地域，默认 ap-guangzhou
            endpoint: 接口域名，默认 aiart.tencentcloudapi.com
        """
        self.secret_id = secret_id or os.getenv("TENCENTCLOUD_SECRET_ID")
        self.secret_key = secret_key or os.getenv("TENCENTCLOUD_SECRET_KEY")
        self.region = region or self.DEFAULT_REGION
        self.endpoint = endpoint or self.DEFAULT_ENDPOINT

        if not self.secret_id or not self.secret_key:
            raise ValueError(
                "请提供腾讯云密钥，或设置环境变量 TENCENTCLOUD_SECRET_ID / TENCENTCLOUD_SECRET_KEY"
            )

        cred = credential.Credential(self.secret_id, self.secret_key)
        http_profile = HttpProfile()
        http_profile.endpoint = self.endpoint
        client_profile = ClientProfile()
        client_profile.httpProfile = http_profile

        self.client = aiart_client.AiartClient(cred, self.region, client_profile)

    # ------------------------------------------------------------------
    # 混元生图 3.0 - 异步
    # ------------------------------------------------------------------
    def submit_text_to_image_job(
        self,
        prompt: str,
        images: Union[str, List[str], None] = None,
        resolution: str = "1024:1024",
        seed: Optional[int] = None,
        logo_add: int = 0,
        revise: int = 1,
    ) -> str:
        """
        提交混元生图 3.0 任务（异步）

        Args:
            prompt: 文本描述，最多 8192 个 utf-8 字符
            images: 参考图（最多 3 张），支持：
                - None: 文生图
                - str: 单张图（URL / 本地路径 / Base64）
                - List[str]: 多张图（最多 3 张）
            resolution: 生成图分辨率（"宽:高"），默认 1024:1024
                文生图：宽高均在 [512, 2048]，宽高乘积 ≤ 1024*1024
            seed: 随机种子（1 ~ 4294967295），不传随机
            logo_add: 1 添加水印，0 不添加，默认 0
            revise: 1 开启 prompt 改写（默认），0 关闭

        Returns:
            任务 ID
        """
        req = models.SubmitTextToImageJobRequest()
        req.Prompt = prompt
        req.Resolution = resolution
        req.LogoAdd = logo_add
        req.Revise = revise

        if images:
            if isinstance(images, str):
                images = [images]
            if len(images) > 3:
                raise ValueError("混元生图 3.0 最多支持 3 张参考图")
            req.Images = [self._normalize_image(img) for img in images]

        if seed is not None:
            req.Seed = seed

        try:
            rsp = self.client.SubmitTextToImageJob(req)
        except TencentCloudSDKException as e:
            raise RuntimeError(f"提交混元生图任务失败: {e}")

        return rsp.JobId

    def query_text_to_image_job(self, job_id: str) -> dict:
        """
        查询混元生图 3.0 任务

        Args:
            job_id: 任务 ID

        Returns:
            {
                "status_code": str,    # 1 等待 / 2 运行 / 4 失败 / 5 完成
                "status_msg": str,
                "error_code": str,
                "error_msg": str,
                "result_image": List[str],   # 完成时返回图片 URL 列表（1 小时有效）
                "revised_prompt": List[str],
            }
        """
        req = models.QueryTextToImageJobRequest()
        req.JobId = job_id

        try:
            rsp = self.client.QueryTextToImageJob(req)
        except TencentCloudSDKException as e:
            raise RuntimeError(f"查询混元生图任务失败: {e}")

        return {
            "status_code": rsp.JobStatusCode,
            "status_msg": rsp.JobStatusMsg,
            "error_code": rsp.JobErrorCode,
            "error_msg": rsp.JobErrorMsg,
            "result_image": list(rsp.ResultImage or []),
            "revised_prompt": list(rsp.RevisedPrompt or []),
        }

    def wait_text_to_image_job(
        self,
        job_id: str,
        interval: float = 3.0,
        timeout: float = 300.0,
    ) -> List[str]:
        """
        轮询等待混元生图 3.0 任务完成

        Args:
            job_id: 任务 ID
            interval: 轮询间隔（秒），默认 3 秒
            timeout: 超时时间（秒），默认 300 秒

        Returns:
            生成图 URL 列表
        """
        deadline = time.time() + timeout
        while True:
            result = self.query_text_to_image_job(job_id)
            status = result["status_code"]

            if status == self.JOB_STATUS_DONE:
                return result["result_image"]
            if status == self.JOB_STATUS_FAILED:
                raise RuntimeError(
                    f"混元生图任务失败: {result['error_code']} - {result['error_msg']}"
                )

            if time.time() >= deadline:
                raise TimeoutError(f"混元生图任务超时（>{timeout}s），job_id={job_id}")

            time.sleep(interval)

    def generate_image(
        self,
        prompt: str,
        images: Union[str, List[str], None] = None,
        resolution: str = "1024:1024",
        seed: Optional[int] = None,
        logo_add: int = 0,
        revise: int = 1,
        interval: float = 3.0,
        timeout: float = 300.0,
    ) -> List[str]:
        """
        混元生图 3.0 一站式（提交 + 轮询 + 返回 URL）

        Returns:
            生成图 URL 列表（1 小时有效，请尽快下载）
        """
        job_id = self.submit_text_to_image_job(
            prompt=prompt,
            images=images,
            resolution=resolution,
            seed=seed,
            logo_add=logo_add,
            revise=revise,
        )
        return self.wait_text_to_image_job(job_id, interval=interval, timeout=timeout)

    # ------------------------------------------------------------------
    # 混元生图 2.0 极速版 - 同步
    # ------------------------------------------------------------------
    def generate_image_rapid(
        self,
        prompt: str,
        image: Optional[str] = None,
        resolution: str = "1024:1024",
        style: Optional[str] = None,
        seed: Optional[int] = None,
        logo_add: int = 0,
        rsp_img_type: str = "url",
    ) -> str:
        """
        混元生图 2.0 极速版（同步，单图返回）

        Args:
            prompt: 文本描述，推荐中文，最多 256 个 utf-8 字符
            image: 参考图（URL 或 本地路径或 Base64），可选
            resolution: 默认 1024:1024，支持比例 1:1/3:4/4:3/9:16/16:9
            style: 风格编号 "1"~"30"，详见文档
            seed: 随机种子
            logo_add: 1 添加水印，0 不添加，默认 0
            rsp_img_type: "url" 或 "base64"，默认 "url"

        Returns:
            URL 或 Base64 字符串
        """
        req = models.TextToImageRapidRequest()
        req.Prompt = prompt
        req.Resolution = resolution
        req.LogoAdd = logo_add
        req.RspImgType = rsp_img_type

        if style:
            req.Style = style
        if seed is not None:
            req.Seed = seed

        if image:
            req.Image = self._normalize_image(image, for_rapid=True)

        try:
            rsp = self.client.TextToImageRapid(req)
        except TencentCloudSDKException as e:
            raise RuntimeError(f"混元生图极速版调用失败: {e}")

        return rsp.ResultImage

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_image(image: str, for_rapid: bool = False):
        """
        标准化图片输入：
        - URL → 直接返回字符串（3.0 接口 Images.N 直接接受 URL/Base64）
        - 本地路径 → 读取并 Base64 编码
        - Base64 字符串（data:image/...;base64,... 或 纯 base64）→ 透传

        对于极速版（for_rapid=True），返回 Image 对象（包含 ImageUrl / ImageBase64 字段）。
        对于 3.0 提交任务，Images.N 是 Array of String，直接返回字符串。
        """
        if image.startswith(("http://", "https://")):
            value, kind = image, "url"
        elif image.startswith("data:"):
            # data:image/png;base64,xxxx
            value, kind = image.split(",", 1)[1], "base64"
        elif os.path.exists(image):
            with open(image, "rb") as f:
                value = base64.b64encode(f.read()).decode("utf-8")
            kind = "base64"
        else:
            # 视为已经是纯 base64 字符串
            value, kind = image, "base64"

        if for_rapid:
            img = models.Image()
            if kind == "url":
                img.ImageUrl = value
            else:
                img.ImageBase64 = value
            return img

        return value


# ============================================================================
# 工具函数
# ============================================================================
def save_image(data: str, output_path: str) -> str:
    """
    保存图片数据到文件

    Args:
        data: 图片 URL 或 Base64 字符串
        output_path: 保存路径
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if data.startswith("http"):
        urllib.request.urlretrieve(data, output_path)
    else:
        if data.startswith("data:"):
            data = data.split(",", 1)[1]
        img_data = base64.b64decode(data)
        with open(output_path, "wb") as f:
            f.write(img_data)
    return output_path


def encode_local_image_base64(file_path: str) -> str:
    """将本地图片编码为 data URI 格式的 Base64"""
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type or not mime_type.startswith("image/"):
        raise ValueError(f"不支持或无法识别的图像格式: {file_path}")
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


# ============================================================================
# 便捷函数
# ============================================================================
def txt2img(
    prompt: str,
    output: str = "output.png",
    resolution: str = "1024:1024",
    use_rapid: bool = False,
    secret_id: str = None,
    secret_key: str = None,
    region: str = None,
) -> List[str]:
    """
    文生图便捷函数

    Args:
        prompt: 文本描述
        output: 输出路径
        resolution: 分辨率，"宽:高"
        use_rapid: True 使用 2.0 极速版（同步），False 使用 3.0（异步）
        secret_id / secret_key / region: 腾讯云凭证

    Returns:
        保存的图片路径列表
    """
    client = TencentHunyuanImage(
        secret_id=secret_id, secret_key=secret_key, region=region
    )

    if use_rapid:
        result = client.generate_image_rapid(prompt=prompt, resolution=resolution)
        return [save_image(result, output)]

    urls = client.generate_image(prompt=prompt, resolution=resolution)
    return _save_urls(urls, output)


def img2img(
    input_images: Union[str, List[str]],
    prompt: str,
    output: str = "output.png",
    resolution: str = "1024:1024",
    use_rapid: bool = False,
    secret_id: str = None,
    secret_key: str = None,
    region: str = None,
) -> List[str]:
    """
    图生图 / 参考图生成便捷函数

    Args:
        input_images: 参考图（URL / 本地路径 / Base64），1~3 张（极速版仅支持 1 张）
        prompt: 文本描述
        output: 输出路径
        resolution: 分辨率
        use_rapid: True 使用 2.0 极速版（仅支持单图，传 Image 参考），False 使用 3.0
        secret_id / secret_key / region: 腾讯云凭证

    Returns:
        保存的图片路径列表
    """
    client = TencentHunyuanImage(
        secret_id=secret_id, secret_key=secret_key, region=region
    )

    if use_rapid:
        single = input_images if isinstance(input_images, str) else input_images[0]
        result = client.generate_image_rapid(
            prompt=prompt, image=single, resolution=resolution
        )
        return [save_image(result, output)]

    urls = client.generate_image(
        prompt=prompt, images=input_images, resolution=resolution
    )
    return _save_urls(urls, output)


def _save_urls(urls: List[str], output: str) -> List[str]:
    if len(urls) == 1:
        return [save_image(urls[0], output)]
    base, ext = os.path.splitext(output)
    return [save_image(u, f"{base}_{i}{ext}") for i, u in enumerate(urls)]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="腾讯云 - 混元生图工具")
    parser.add_argument("--mode", "-m", choices=["txt2img", "img2img"], default="txt2img", help="模式")
    parser.add_argument("--prompt", "-p", required=True, help="文本描述")
    parser.add_argument("--input", "-i", action="append", default=[],
                        help="参考图（URL / 本地路径），可指定多次（最多 3 张）")
    parser.add_argument("--output", "-o", default="output.png", help="输出文件路径")
    parser.add_argument("--resolution", "-r", default="1024:1024", help="分辨率，宽:高")
    parser.add_argument("--rapid", action="store_true", help="使用 2.0 极速版（同步）")
    parser.add_argument("--secret-id", help="腾讯云 SecretId")
    parser.add_argument("--secret-key", help="腾讯云 SecretKey")
    parser.add_argument("--region", default=None, help="地域，默认 ap-guangzhou")

    args = parser.parse_args()

    if args.mode == "txt2img":
        paths = txt2img(
            prompt=args.prompt,
            output=args.output,
            resolution=args.resolution,
            use_rapid=args.rapid,
            secret_id=args.secret_id,
            secret_key=args.secret_key,
            region=args.region,
        )
    else:
        if not args.input:
            print("错误：图生图模式需要至少一张 --input 图片")
            exit(1)
        paths = img2img(
            input_images=args.input if len(args.input) > 1 else args.input[0],
            prompt=args.prompt,
            output=args.output,
            resolution=args.resolution,
            use_rapid=args.rapid,
            secret_id=args.secret_id,
            secret_key=args.secret_key,
            region=args.region,
        )

    for p in paths:
        print(f"生成成功: {p}")
