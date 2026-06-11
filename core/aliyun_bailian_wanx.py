"""
阿里云百炼 - 万相图像生成与编辑 2.7 API Python 工具

支持：
- 文生图：传入 text，可选 0 张 image
- 图生图 / 多图融合：传入 text + 1~9 张 image
- 同一接口统一处理（万相 2.7 的特色）

参考文档：
- 万相 2.7 图像生成与编辑：https://help.aliyun.com/zh/model-studio/wan-image-generation-and-editing-api-reference
- 图像编辑：https://help.aliyun.com/zh/model-studio/wan-image-edit

前置条件：
- pip install -U dashscope  (需要 >= 1.25.15)
- 环境变量 DASHSCOPE_API_KEY 设置为百炼 API Key（sk-xxx 格式）
"""

import os
import base64
import mimetypes
import urllib.request
from pathlib import Path
from typing import Optional, List, Union

try:
    import dashscope
    from dashscope.aigc.image_generation import ImageGeneration
    from dashscope.api_entities.dashscope_response import Message
except ImportError:
    print("请安装 DashScope SDK: pip install -U dashscope")
    raise


class AliyunWan27:
    """阿里云百炼 - 万相 2.7 图像生成与编辑封装"""

    # 万相 2.7 模型
    MODEL_PRO = "wan2.7-image-pro"   # 专业版，文生图支持 4K
    MODEL_FAST = "wan2.7-image"      # 速度更快版，最高 2K

    # 北京地域 base_url（默认）
    BASE_URL_BJ = "https://dashscope.aliyuncs.com/api/v1"

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
    ):
        """
        初始化百炼万相 2.7 客户端

        Args:
            api_key: 百炼 API Key（sk-xxx 格式），默认从环境变量 DASHSCOPE_API_KEY 获取
            base_url: API 地址，默认北京地域
        """
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ValueError("请提供百炼 API Key，或设置环境变量 DASHSCOPE_API_KEY（sk-xxx 格式）")

        # 设置 base_url
        dashscope.base_http_api_url = base_url or self.BASE_URL_BJ
        dashscope.api_key = self.api_key

    def generate_image(
        self,
        prompt: str,
        images: Union[str, List[str], None] = None,
        model: str = None,
        size: str = "2K",
        n: int = 1,
        watermark: bool = False,
        thinking_mode: bool = True,
        negative_prompt: str = None,
        seed: Optional[int] = None,
    ) -> List[str]:
        """
        万相 2.7 图像生成与编辑（同步调用）

        Args:
            prompt: 文本描述/编辑指令（最长 5000 字符）
            images: 输入图片（可选，0~9 张）
                - None / 空: 纯文生图
                - str: 单张图（URL / 本地路径 / Base64）
                - List[str]: 多张图（最多 9 张）
                支持的输入格式：
                - 公网 URL: "https://example.com/image.jpg"
                - 本地文件: "/abs/path/to/image.png"（会自动转换为 file:// 协议）
                - Base64: "data:image/png;base64,xxx"
            model: 模型名，默认 wan2.7-image-pro
            size: 图片尺寸，"1K"/"2K"(默认)/"4K"，或 "1024*1024" 等具体像素
                  注意：图像编辑场景最高 2K
            n: 生成数量（1~4）
            watermark: 是否添加水印
            thinking_mode: 思考模式（默认开启）
            negative_prompt: 反向提示词（不希望出现的元素）
            seed: 随机种子

        Returns:
            生成的图片 URL 列表（24 小时有效，请尽快下载）
        """
        model = model or self.MODEL_PRO

        # 构建 content：text + 0~9 张 image
        content = [{"text": prompt}]

        if images:
            if isinstance(images, str):
                images = [images]
            for img in images:
                content.append({"image": self._normalize_image(img)})

        message = Message(role="user", content=content)

        # 构建可选参数
        kwargs = {
            "model": model,
            "api_key": self.api_key,
            "messages": [message],
            "n": n,
            "size": size,
            "watermark": watermark,
        }

        if thinking_mode is not None:
            kwargs["thinking_mode"] = thinking_mode
        if negative_prompt:
            kwargs["negative_prompt"] = negative_prompt
        if seed is not None:
            kwargs["seed"] = seed

        try:
            rsp = ImageGeneration.call(**kwargs)
        except Exception as e:
            raise RuntimeError(f"图像生成调用失败: {e}")

        if rsp.status_code != 200:
            raise RuntimeError(
                f"图像生成失败: status_code={rsp.status_code}, "
                f"code={getattr(rsp, 'code', '')}, message={getattr(rsp, 'message', '')}"
            )

        # 提取图片 URL
        urls = []
        for choice in rsp.output.choices:
            for content_item in choice["message"]["content"]:
                if content_item.get("type") == "image":
                    urls.append(content_item["image"])

        if not urls:
            raise RuntimeError(f"未返回图片 URL: {rsp}")

        return urls

    @staticmethod
    def _normalize_image(image: str) -> str:
        """
        标准化图片输入：
        - URL / Base64 / file:// 直接返回
        - 本地路径自动加 file:// 前缀（绝对路径）
        """
        if image.startswith(("http://", "https://", "file://", "data:")):
            return image
        # 视为本地路径
        abs_path = os.path.abspath(image)
        return f"file://{abs_path}"


# ============================================================================
# 工具函数
# ============================================================================
def save_image(url: str, output_path: str) -> str:
    """下载图片 URL 到本地"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if url.startswith("http"):
        urllib.request.urlretrieve(url, output_path)
    else:
        # Base64
        if url.startswith("data:"):
            url = url.split(",", 1)[1]
        img_data = base64.b64decode(url)
        with open(output_path, "wb") as f:
            f.write(img_data)
    return output_path


def encode_local_image_base64(file_path: str) -> str:
    """将本地图片编码为 Base64 (data:image/xxx;base64,xxx 格式)"""
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
    model: str = None,
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
    api_key: str = None,
) -> List[str]:
    """
    文生图便捷函数

    Args:
        prompt: 文本描述
        output: 输出路径
        model: 模型名，默认 wan2.7-image-pro
        size: 尺寸，1K / 2K / 4K 或 1024*1024
        n: 数量
        watermark: 是否水印
        api_key: API Key

    Returns:
        保存的图片路径列表
    """
    client = AliyunWan27(api_key=api_key)
    urls = client.generate_image(
        prompt=prompt,
        model=model,
        size=size,
        n=n,
        watermark=watermark,
    )

    if n == 1 and len(urls) == 1:
        return [save_image(urls[0], output)]

    base, ext = os.path.splitext(output)
    saved = []
    for i, url in enumerate(urls):
        path = f"{base}_{i}{ext}"
        saved.append(save_image(url, path))
    return saved


def img2img(
    input_images: Union[str, List[str]],
    prompt: str,
    output: str = "output.png",
    model: str = None,
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
    api_key: str = None,
) -> List[str]:
    """
    图生图 / 多图融合便捷函数

    Args:
        input_images: 输入图片，1~9 张（URL / 本地路径 / Base64）
        prompt: 编辑指令
        output: 输出路径
        model: 模型名，默认 wan2.7-image-pro
        size: 尺寸（图像编辑最高 2K）
        n: 数量
        watermark: 是否水印
        api_key: API Key

    Returns:
        保存的图片路径列表
    """
    client = AliyunWan27(api_key=api_key)
    urls = client.generate_image(
        prompt=prompt,
        images=input_images,
        model=model,
        size=size,
        n=n,
        watermark=watermark,
    )

    if n == 1 and len(urls) == 1:
        return [save_image(urls[0], output)]

    base, ext = os.path.splitext(output)
    saved = []
    for i, url in enumerate(urls):
        path = f"{base}_{i}{ext}"
        saved.append(save_image(url, path))
    return saved


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="阿里云百炼 - 万相 2.7 图像生成与编辑工具")
    parser.add_argument("--mode", "-m", choices=["txt2img", "img2img"], default="txt2img", help="模式")
    parser.add_argument("--prompt", "-p", required=True, help="文本描述/编辑指令")
    parser.add_argument("--input", "-i", action="append", default=[],
                        help="输入图片（URL / 本地路径），图生图模式必填，可指定多次叠加")
    parser.add_argument("--output", "-o", default="output.png", help="输出文件路径")
    parser.add_argument("--model", default=None,
                        help="模型名，默认 wan2.7-image-pro，可选 wan2.7-image")
    parser.add_argument("--size", "-s", default="2K", help="尺寸 1K/2K/4K 或 1024*1024")
    parser.add_argument("--n", type=int, default=1, help="生成数量")
    parser.add_argument("--watermark", action="store_true", help="添加水印")
    parser.add_argument("--api-key", help="百炼 API Key（sk-xxx）")

    args = parser.parse_args()

    if args.mode == "txt2img":
        paths = txt2img(
            prompt=args.prompt,
            output=args.output,
            model=args.model,
            size=args.size,
            n=args.n,
            watermark=args.watermark,
            api_key=args.api_key,
        )
    else:
        if not args.input:
            print("错误：图生图模式需要至少一张 --input 图片")
            exit(1)
        paths = img2img(
            input_images=args.input if len(args.input) > 1 else args.input[0],
            prompt=args.prompt,
            output=args.output,
            model=args.model,
            size=args.size,
            n=args.n,
            watermark=args.watermark,
            api_key=args.api_key,
        )

    for p in paths:
        print(f"生成成功: {p}")
