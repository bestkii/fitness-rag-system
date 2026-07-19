#!/usr/bin/env python3
"""
Fitness RAG Mock Data Generator — Async Synthetic Data Generator
================================================================
Generates 3,000 high-quality fitness myth-busting QA pairs via DeepSeek API.
- asyncio + aiohttp with Semaphore(5) rate limiting
- tenacity exponential backoff retry on HTTP 429 / network errors
- Append-mode JSONL for crash recovery (断点续传)
- Dynamic 12-topic pool, 2 random topics per request
- Enforced JSON structured output (expert, rumor, truth)
- Real-time progress reporting every 50 records
- Final summary statistics

Requirements:
  pip install aiohttp tenacity

Usage:
  set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
  python async_fitness_data_generator.py

Output: fitness_mock_3000.jsonl
"""

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

import aiohttp
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# ──────────────────────────────────────────────────────────────────────
# 0. 配置常量
# ──────────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not API_KEY:
    print("[FATAL] 请设置环境变量 DEEPSEEK_API_KEY")
    print("  Windows: set DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx")
    print("  Linux/Mac: export DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx")
    sys.exit(1)

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"           # DeepSeek-V3
TEMPERATURE = 0.8                 # 适度随机性保证多样性
MAX_TOKENS = 1024                 # 每条响应最大token数
CONCURRENCY = 5                   # asyncio.Semaphore 限制并发数
TOTAL_TARGET = 3000               # 目标生成总数
OUTPUT_FILE = "fitness_mock_3000.jsonl"
ALLOWED_EXPERTS = {
    "exercise_physiology",
    "clinical_nutrition",
    "media_discourse",
    "sports_biomechanics",
    "corrective_exercise",
    "sports_medicine",
    "sports_nutrition",
}

# ──────────────────────────────────────────────────────────────────────
# 1. 动态主题轮询池 — 12 个健身子维度
# ──────────────────────────────────────────────────────────────────────
TOPIC_POOL = [
    {
        "id": "mass_gain",
        "zh": "健美与瘦体重增长",
        "en": "Bodybuilding & Lean Mass Gain",
        "desc": "增肌训练频率、蛋白质 timing、合成窗口、增肌期饮食策略类谣言",
    },
    {
        "id": "strength_myths",
        "zh": "高强度力量训练辟谣",
        "en": "High-Intensity Strength Training Myth-busting",
        "desc": "训练至力竭、每天冲极限、过度训练综合征、强度与频率误区",
    },
    {
        "id": "big_lifts",
        "zh": "三大项动作力学误区",
        "en": "Big Three Lifting Mechanics Misconceptions",
        "desc": "深蹲膝盖过脚尖、硬拉弓背、卧推起桥、杠铃路径等动作力学谣言",
    },
    {
        "id": "nutrition_tracking",
        "zh": "饮食热量与宏量营养素追踪陷阱",
        "en": "Calorie & Macronutrient Tracking Pitfalls",
        "desc": "代谢适应、NEAT 消耗、食物秤误差、碳水/脂肪比例极端推荐",
    },
    {
        "id": "metabolic_truth",
        "zh": "增肌与减脂期代谢真相",
        "en": "Metabolic Truths During Bulking & Cutting",
        "desc": "饥饿模式、代谢损伤、反向饮食、设定点理论等代谢类谣言",
    },
    {
        "id": "cardio_fat_loss",
        "zh": "有氧运动与减脂关系",
        "en": "Cardio & Fat Loss Relationship",
        "desc": "局部减脂、空腹有氧神话、稳态 vs HIIT 优劣、有氧掉肌肉",
    },
    {
        "id": "supplements",
        "zh": "补剂与蛋白粉真相",
        "en": "Supplements & Protein Powder Truths",
        "desc": "BCAA 必要性、减脂特效补剂、排毒茶、胶原蛋白、专利混合配方",
    },
    {
        "id": "recovery",
        "zh": "拉伸与恢复伪科学",
        "en": "Stretching & Recovery Pseudoscience",
        "desc": "训练前静态拉伸、冷冻疗法、泡沫轴神奇功效、筋膜放松谬误",
    },
    {
        "id": "women_fitness",
        "zh": "女性健身误区",
        "en": "Women's Fitness Misconceptions",
        "desc": "举铁变壮、腿缝训练、塑形 vs 增肌、孕期运动安全性",
    },
    {
        "id": "meal_timing",
        "zh": "饮食时间与频率迷思",
        "en": "Meal Timing & Frequency Myths",
        "desc": "一天6餐必要性、睡前进食致胖、合成窗口、间歇断食夸大声称",
    },
    {
        "id": "posture",
        "zh": "体态与纠正训练误区",
        "en": "Posture & Corrective Exercise Myths",
        "desc": "完美体态神话、翼状肩胛矫正、骨盆前倾恐慌、脊柱中立教条",
    },
    {
        "id": "injury_prevention",
        "zh": "运动损伤预防谣言",
        "en": "Injury Prevention Myths",
        "desc": "腰带保安全、缠膝神话、拉伸预防损伤、极简鞋万能论",
    },
]


# ──────────────────────────────────────────────────────────────────────
# 2. 线程安全的 JSONL 追加写入器（断点续传核心）
# ──────────────────────────────────────────────────────────────────────
class AtomicJsonlWriter:
    """异步安全的 JSONL 追加写入器。

    使用 asyncio.Lock 保证多协程并发写入时不会出现行交错。
    打开文件时用 'a' 模式，天然支持断点续传。
    """

    def __init__(self, path: str):
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    async def write(self, record: dict) -> None:
        """原子化追加一条 JSON 行。"""
        async with self._lock:
            line = json.dumps(record, ensure_ascii=False) + "\n"
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line)
            self._count += 1

    async def count_existing(self) -> int:
        """统计已有行数（用于启动时断点续传检测）。"""
        if not self.path.exists():
            return 0
        async with self._lock:
            with open(self.path, "r", encoding="utf-8") as f:
                for _ in f:
                    self._count += 1
        return self._count


# ──────────────────────────────────────────────────────────────────────
# 3. DeepSeek API 调用 + Tenacity 自动重试
# ──────────────────────────────────────────────────────────────────────
class RateLimitError(Exception):
    """HTTP 429 — 触发 tenacity 指数退避重试。"""


class APIResponseError(Exception):
    """API 返回非 200 或 JSON 解析失败。"""


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type(
        (RateLimitError, aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError)
    ),
    reraise=True,
)
async def call_deepseek(
    session: aiohttp.ClientSession,
    system_prompt: str,
    user_prompt: str,
) -> dict:
    """单次 DeepSeek Chat API 调用（不含 Semaphore——由外层控制）。

    此函数被 @retry 装饰，遇到 RateLimit / ClientError / Timeout 时
    自动以指数退避重试，最多 5 次。

    Returns:
        解析后的 JSON dict，必须包含 expert / rumor / truth 三个键。
    """
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    async with session.post(
        API_URL,
        json=payload,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=120),
    ) as resp:
        body = await resp.text()

        if resp.status == 429:
            retry_after = resp.headers.get("Retry-After", "5")
            print(f"    [429] 触发限流，等待 {retry_after}s 后重试 ...")
            raise RateLimitError(f"Rate limited: {body[:100]}")

        if resp.status != 200:
            raise APIResponseError(f"HTTP {resp.status}: {body[:200]}")

        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]

        # 强制解析 JSON 对象
        result = json.loads(content)

        # 验证必含字段
        required = {"expert", "rumor", "truth"}
        missing = required - set(result.keys())
        if missing:
            raise APIResponseError(
                f"缺少必含键 {missing}: {json.dumps(result, ensure_ascii=False)[:200]}"
            )
        if result["expert"] not in ALLOWED_EXPERTS:
            raise APIResponseError(f"Invalid expert label: {result['expert']!r}")

        return result


# ──────────────────────────────────────────────────────────────────────
# 4. 提示词工程
# ──────────────────────────────────────────────────────────────────────
def build_system_prompt() -> str:
    return (
        "You are a professional fitness and nutrition fact-checking system. "
        "You MUST respond with a valid JSON object containing exactly three keys:\n"
        '  - "expert": one of ["exercise_physiology", "clinical_nutrition", '
        '"media_discourse", "sports_biomechanics", "corrective_exercise", '
        '"sports_medicine"]\n'
        '  - "rumor": the social-media-style misinformation claim (1-2 sentences, '
        "written as a realistic social media post, may include hashtags)\n"
        '  - "truth": the scientific fact-based rebuttal (2-4 sentences, '
        "reference specific physiological mechanisms and evidence)\n\n"
        "Guidelines:\n"
        "- The rumor must sound viral and credible to a layperson — use urgency, "
        "absolutes ('never', 'always', 'everyone'), and social proof\n"
        "- The truth must be precise and cite specific mechanisms (e.g., 'mTOR "
        "signaling pathway', 'net energy balance', 'Type II muscle fiber "
        "recruitment')\n"
        "- Assign the most appropriate expert based on the claim's primary domain\n"
        "- Generate diverse examples — do NOT repeat the same myth structure\n"
        "- Return ONLY the JSON object, no markdown fences, no extra text"
    )


def build_user_prompt(topic_a: dict, topic_b: dict) -> str:
    return (
        f"Generate one fitness misinformation claim and its scientific rebuttal.\n\n"
        f"Primary topic: {topic_a['zh']} — {topic_a['en']}\n"
        f"Secondary topic: {topic_b['zh']} — {topic_b['en']}\n\n"
        f"Combine elements from BOTH topics into ONE realistic social media post. "
        f"The claim should feel like something trending on Xiaohongshu, Douyin, "
        f"Weibo, Instagram, or TikTok.\n\n"
        f"Output format:\n"
        f'{{"expert": "<best_fitting_expert>", '
        f'"rumor": "<social_media_claim_sentence>", '
        f'"truth": "<scientific_rebuttal_with_mechanisms>"}}\n\n'
        f"Now generate an original claim combining {topic_a['zh']} "
        f"and {topic_b['zh']}. Be creative and specific."
    )


# ──────────────────────────────────────────────────────────────────────
# 5. 单条数据生成 Worker
# ──────────────────────────────────────────────────────────────────────
async def generate_one(
    worker_id: int,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
    writer: AtomicJsonlWriter,
    system_prompt: str,
    progress: list,
) -> dict | None:
    """生成一条记录：随机选取 2 个主题 → 调用 API → 写入 JSONL。

    在 Semaphore 保护下执行（含重试），避免触发 Rate Limit。
    """
    topics = random.sample(TOPIC_POOL, 2)
    user_prompt = build_user_prompt(topics[0], topics[1])

    # Semaphore 在外层控制并发数，确保同时最多 5 个活跃请求
    async with semaphore:
        try:
            result = await call_deepseek(session, system_prompt, user_prompt)

            # 富化元数据
            record = {
                "index": None,  # 由主协程在收尾时统一编号
                "topics": [topics[0]["id"], topics[1]["id"]],
                "topics_zh": [topics[0]["zh"], topics[1]["zh"]],
                "expert": result["expert"],
                "rumor": result["rumor"],
                "truth": result["truth"],
                "model": MODEL,
                "temperature": TEMPERATURE,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
            await writer.write(record)
            progress[0] += 1
            done = progress[0]
            if done % 50 == 0:
                elapsed_sofar = time.time() - progress[1]
                rate = done / elapsed_sofar if elapsed_sofar > 0 else 0
                remaining_count = TOTAL_TARGET - done
                eta = remaining_count / rate if rate > 0 else 0
                print(f"  [进展] {done}/{TOTAL_TARGET}  |  速率 {rate:.1f}条/s  |  预计剩余 {eta:.0f}s")
            return record

        except Exception as e:
            print(f"  [Worker {worker_id:03d}] 已达最大重试次数，放弃: {e}")
            return None


# ──────────────────────────────────────────────────────────────────────
# 6. 主协程
# ──────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 62)
    print("  🏋️  Fitness RAG — Async Synthetic Data Generator")
    print(f"  🎯  目标: {TOTAL_TARGET} 条  |  📁 输出: {OUTPUT_FILE}")
    print(f"  🤖  模型: {MODEL}  |  🌡️  Temp: {TEMPERATURE}")
    print(f"  ⛓️   并发: Semaphore({CONCURRENCY})  |  🔁 重试: 指数退避×5")
    print(f"  📚 主题池: {len(TOPIC_POOL)} 个子维度，每次随机组合 2 个")
    print("=" * 62)

    # ── 断点续传：统计已有记录数 ──
    writer = AtomicJsonlWriter(OUTPUT_FILE)
    existing = await writer.count_existing()
    remaining = TOTAL_TARGET - existing

    if existing > 0:
        # 检查最后一行是否为 _meta 完成标记
        lines = []
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
        if lines and '"completed_at"' in lines[-1]:
            print(f"\n  ⚠️  检测到完成标记，已有 {existing - 1} 条有效记录 + 元数据")
            print(f"  如需重新生成请删除 {OUTPUT_FILE} 或增大 TOTAL_TARGET")
            return
        print(f"\n  🔄 检测到 {existing} 条已有记录，继续生成 {remaining} 条 ...\n")
    else:
        print(f"\n  🆕 从零开始生成 {TOTAL_TARGET} 条数据\n")

    if remaining <= 0:
        print(f"  ✅ 已有 {existing} 条，达到目标 {TOTAL_TARGET}，无需继续。")
        return

    semaphore = asyncio.Semaphore(CONCURRENCY)
    system_prompt = build_system_prompt()
    # progress[0] = counter, progress[1] = start_time
    progress = [0, time.time()]

    # TCP 连接池优化
    connector = aiohttp.TCPConnector(
        limit=CONCURRENCY + 2,   # 略微超过 Semaphore，避免连接池饥饿
        ttl_dns_cache=300,       # DNS 缓存 5 分钟
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        print(f"  启动 {remaining} 个并发任务 ...\n")

        # 创建所有任务，Semaphore 会自动排队限制并发
        tasks = [
            asyncio.create_task(
                generate_one(i, session, semaphore, writer, system_prompt, progress)
            )
            for i in range(remaining)
        ]

        # 等待全部完成
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time
        successful = sum(1 for r in results if r is not None)

    # ── 最终统计 ──
    total = existing + successful
    print("\n" + "=" * 62)
    print(f"  ✅ 生成完成!")
    print(f"  📄 文件: {OUTPUT_FILE}")
    print(f"  📊 总计: {total} 条 (已有 {existing} + 新增 {successful})")

    if elapsed > 0 and successful > 0:
        print(f"  ⏱️  耗时: {elapsed:.1f} 秒")
        print(f"  ⚡ 速率: {successful / elapsed:.1f} 条/秒")
        print(f"  ⏳ 平均: {elapsed / successful:.2f} 秒/条")

    if successful < remaining:
        print(f"  ❌ 失败: {remaining - successful} 条")
        print(f"  💡 重新运行脚本将从断点处继续")
    else:
        print(f"  🎉 全部成功!")

    # ── 写入元数据脚标（标记完成） ──
    meta_record = {
        "_meta": {
            "total_records": total,
            "target": TOTAL_TARGET,
            "newly_generated": successful,
            "failures": remaining - successful,
            "elapsed_seconds": round(elapsed, 1),
            "throughput_per_sec": round(successful / elapsed, 1) if elapsed > 0 else 0,
            "model": MODEL,
            "temperature": TEMPERATURE,
            "concurrency": CONCURRENCY,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
    }
    async with writer._lock:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(meta_record, ensure_ascii=False) + "\n")

    print("=" * 62)


if __name__ == "__main__":
    asyncio.run(main())
