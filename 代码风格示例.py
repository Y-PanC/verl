import openai
import json
from tqdm import tqdm
import copy
import os
import time
import glob
import re
import logging
from typing import Dict, List, Tuple, Optional
from copy import deepcopy
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type
)
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import random  # <<<<<<< 新增：用于随机抽样
from skill_manager import SkillManager

import threading # <<<<<<< 新增导入
# 将当前脚本所在的目录添加到 Python 搜索路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- 配置日志系统 ---
def setup_logging():
    """配置logging系统"""
    # 创建logger
    logger = logging.getLogger('bt_Session')
    logger.setLevel(logging.DEBUG)

    # 清除已有的handlers
    logger.handlers.clear()

    # 创建formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件handler
    file_handler = logging.FileHandler('/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/session5.log', mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    # logger.addHandler(file_handler)

    return logger

# 初始化logger
logger = setup_logging()

# tee.py - 保留用于兼容性，但主要使用logging系统
class Tee:
    def __init__(self, *files):
        self.files = files

    def write(self, text):
        for f in self.files:
            f.write(text)
            f.flush()  # 立即写入

    def flush(self):
        for f in self.files:
            f.flush()


def custom_wait_strategy(retry_state):
    """
    自定义的tenacity等待策略。
    如果遇到 429 错误，就等待更长的时间；否则，使用标准指数退避。
    """
    exception = retry_state.outcome.exception()
    
    is_rate_limit = False
    if isinstance(exception, openai.RateLimitError):
        is_rate_limit = True
    elif isinstance(exception, openai.APIStatusError) and exception.status_code == 429:
        is_rate_limit = True

    if is_rate_limit:
        attempt = retry_state.attempt_number
        # 对 429 错误使用更长的等待时间 (15秒, 30秒, 45秒, ...)
        wait_time = min(30 * attempt, 60) # 15秒递增，最多等60秒
        logger.warning(f" ↪️ [429] Rate Limit! 触发第 {attempt} 次重试, 将等待 {wait_time} 秒...")
        return wait_time
    else:
        # 对于所有其他错误，使用标准的1-30秒随机指数退避
        return wait_random_exponential(min=1, max=30)(retry_state)
    


class Config:
    """集中管理所有配置信息"""

    API_KEY = "sk-ogOhHmD6PRSSKsx8Tch63KhIXlwKaofCJsh7VlJAkzw7nzmp"
    BASE_URL = "http://35.220.164.252:3888/v1/"
    API_MODEL = "gpt-5"
    
    # 路径设置
    INPUT_DIR = '/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/unintake/test/client_info'
    OUTPUT_DIR = '/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/unintake/test/output'
    PROMPT_DIR = '/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/unintake/prompt'

    PROMPT_FILES = {
        'goals_session1': 'goals_session1.txt',
        'goals': 'goals.txt',
        'goals1': 'goals1.txt',
        'goals2': 'goals2.txt',
        'goals3': 'goals3.txt',
        'dialogue1': 'dialogue1.txt',
        'dialogue2': 'dialogue2.txt',
        'dialogue3': 'dialogue3.txt',
        'check_remake': 'check_remake.txt',
        'skills': 'skills.txt',
        'summary': 'summary.txt',
        'client_merge': 'client_merge.txt',
        'client_get': 'client_get.txt'
    }
    
    LOG_FILE_PATH = os.path.join(OUTPUT_DIR, '_success_log.txt')

    # 多线程设置
    MAX_WORKERS = 100



# --- 2. API处理模块 (API Handler Module) ---
class APIHandler:
    """封装所有与LLM API的交互，使用openai库并集成tenacity重试机制"""


    def __init__(self, config):
        self.config = config
        try:
            # 初始化 OpenAI 客户端 (v1.0.0+ 标准方式)
            self.client = openai.OpenAI(
                api_key=self.config.API_KEY,
                base_url=self.config.BASE_URL,
            )
        except Exception as e:
            raise ValueError(f"OpenAI 客户端初始化失败: {e}")


    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(5),
        wait=wait_random_exponential(min=1, max=30)
    )
    def _chat_completion_with_retries(self, messages):
        """带重试逻辑的API调用封装"""
        logger.debug("  -> 正在尝试调用 OpenAI API...")
        try:
            response = self.client.chat.completions.create(
                model=self.config.API_MODEL,
                messages=messages,
                response_format={"type": "json_object"},
                timeout=500 # 设置请求超时
            )
            logger.debug("  ✅ API 调用成功!")
            return response
        except Exception as e:
            logger.warning(f"  ↪️ API 调用中发生错误: {e}. Tenacity将尝试重连...")
            raise # 抛出异常以触发tenacity的重试

    def call(self, prompt, input_data):
        """
        构建消息并调用带重试逻辑的API函数
        """
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(input_data, ensure_ascii=False, indent=2)}
        ]

        try:
            response = self._chat_completion_with_retries(messages)
            return self._parse_response(response)
        except Exception as e:
            # 如果所有重试都失败了，捕获最终异常
            logger.error(f"❌ API 请求最终失败 (所有重试均告失败): {e}")
            return None



    def call_with_history(self, system_prompt, user_input_data, history_messages=None):
        """
        支持多轮对话历史的API调用

        Args:
            system_prompt: 系统提示词
            user_input_data: 当前用户输入数据
            history_messages: 历史消息列表，格式为[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]

        Returns:
            dict: API响应的JSON解析结果
        """
        messages = [
            {"role": "system", "content": system_prompt}
        ]

        # 添加历史消息
        if history_messages:
            messages.extend(history_messages)

        # 添加当前输入
        messages.append({"role": "user", "content": json.dumps(user_input_data, ensure_ascii=False, indent=2)})

        try:
            response = self._chat_completion_with_retries(messages)
            return self._parse_response(response)
        except Exception as e:
            # 如果所有重试都失败了，捕获最终异常
            logger.error(f"❌ 带历史的API请求最终失败 (所有重试均告失败): {e}")
            return None

    def _parse_response(self, response):
        """解析来自openai库的成功响应"""
        try:
            usage = response.usage
            if usage:
                logger.debug(
                    f"  📊 Token usage: "
                    f"Prompt={usage.prompt_tokens}, "
                    f"Completion={usage.completion_tokens}, "
                    f"Total={usage.total_tokens}"
                )

            content_str = response.choices[0].message.content
            return json.loads(content_str)
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"❌ 错误: 解析API响应JSON失败. 错误: {e}")
            logger.debug(f"    原始响应内容: {response.choices[0].message.content}")
            return None

# --- 3. 数据管理模块 (Data Manager Module) ---
class DataManager:
    """负责所有文件和数据操作"""
    def __init__(self, config):
        self.config = config
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        self.log_lock = threading.Lock()  

    def load_prompts(self):
        prompts = {}
        for key, filename in self.config.PROMPT_FILES.items():
            path = os.path.join(self.config.PROMPT_DIR, filename)
            if not os.path.exists(path):
                logger.warning(f"⚠️ 警告: Prompt文件 '{path}' 未找到，将跳过加载。")
                continue
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    prompts[key] = f.read()
                    logger.info(f"📄 已成功加载Prompt: '{key}'")
            except Exception as e:
                logger.error(f"❌ 错误: 读取文件 '{path}' 时发生意外错误: {e}")
                return None
        return prompts

    def get_files_to_process(self): 
        all_files = glob.glob(os.path.join(self.config.INPUT_DIR, '*.json'))
        try:
            with open(self.config.LOG_FILE_PATH, 'r', encoding='utf-8') as f:
                processed_files = {line.strip() for line in f}
            logger.info(f"📖 已加载最终完成记录，{len(processed_files)}个文件已完成。")
        except FileNotFoundError:
            processed_files = set()
            logger.info("📄 未找到最终完成日志，将开始全新处理。")

        files_to_process = [f for f in all_files if os.path.basename(f) not in processed_files]
        logger.info(f"🔍 发现 {len(all_files)} 个总文件, {len(files_to_process)} 个文件待处理。")
        return files_to_process 

    def load_client_data(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ 读取源文件 {os.path.basename(file_path)} 失败: {e}")
            return None

    def load_or_initialize_progress(self, client_data, filename):
        """
        加载已有的进度文件，如果不存在则根据源数据初始化。
        能抵御进度文件损坏的风险，若加载失败则从头开始。
        """
        output_path = os.path.join(self.config.OUTPUT_DIR, filename)
        if os.path.exists(output_path):
            try:
                with open(output_path, 'r', encoding='utf-8') as f:
                    logger.info(f"  -> 发现并加载已有进度: {filename}")
                    return json.load(f)
            except Exception as e:
                logger.warning(f"  -> 警告: 加载进度文件 {filename} 失败: {e}。将重新开始。")

        # 如果没有进度文件或加载失败，则初始化
        return {
            "client_id": client_data.get("user_id"),
            "theoretical": client_data.get("theoretical"),
            "client_info": {key: client_data.get(key, "") for key in [
                "static_traits", "main_problem", "topic",  "growth_experiences", "core_demands", "target_behavior"
            ]},
            "global_plan": client_data.get("plan", ""),
            "sessions": []
        }

    def save_progress(self, progress_data, filename):
        """将当前进度保存（覆盖）到输出文件"""
        output_path = os.path.join(self.config.OUTPUT_DIR, filename)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, indent=4, ensure_ascii=False)
            return True
        except IOError as e:
            logger.error(f"❌ 保存进度到 {output_path} 失败: {e}")
            return False

    def log_completion(self, filename):
        """在最终完成日志中记录一个文件名 (线程安全)"""  # <<<<<<< 修改
        with self.log_lock:  # <<<<<<< 修改：使用锁来确保写入的原子性
            with open(self.config.LOG_FILE_PATH, 'a', encoding='utf-8') as log_f:
                log_f.write(f"{filename}\n")
        logger.info(f"[COMPLETE] 文件 {filename} 已标记为最终完成!")


# --- 4. 核心业务逻辑模块 (Core Logic Module) ---
class SessionGenerator:
    """处理单个来访者的完整多轮咨询生成流程"""

    def __init__(self, api_handler, prompts, data_manager):
        self.api_handler = api_handler
        self.prompts = prompts
        self.data_manager = data_manager

    import re

    def _get_max_session_from_plan(self, global_plan):
        """
        从global_plan中获取最大session数
        (已更新, 适应新的 'content' 字典结构)

        Args:
            global_plan (list): 来访者的治疗计划，包含各阶段的sessions范围

        Returns:
            int: 最大session数
        """
        if not global_plan or not isinstance(global_plan, list):
            return 10  # 默认最大值

        max_session = 0
        
        for stage_info in global_plan:
            if not isinstance(stage_info, dict):
                continue

            # 新的逻辑：遍历 'content' 字典的键
            content_dict = stage_info.get("content")
            if not isinstance(content_dict, dict):
                # 如果没有 'content' 或 'content' 不是字典，则跳过
                continue  

            for session_key in content_dict.keys():
                # session_key 示例: "第1次_session_content", "第2次_session_content"
                if not isinstance(session_key, str):
                    continue
                
                # 提取键中的第一个数字
                # re.search 会找到第一个匹配的数字序列
                match = re.search(r'\d+', session_key)
                
                if match:
                    try:
                        # 将找到的数字字符串转换为整数
                        session_num = int(match.group(0))
                        max_session = max(max_session, session_num)
                    except ValueError:
                        # 如果转换失败（虽然 \d+ 应该能保证），则跳过
                        continue

        # 如果遍历后 max_session 仍然是 0 (例如 global_plan 为空或格式完全错误)
        # 则返回默认值 10，否则返回找到的最大值
        return max_session if max_session > 0 else 10

    def _determine_stage_by_session_num(self, session_num, global_plan):
        """
        根据会话次数和来访者个人plan确定当前所属的治疗阶段

        Args:
            session_num (int): 当前会话次数
            global_plan (list): 来访者的治疗计划，包含各阶段的sessions范围

        Returns:
            int: 当前阶段编号 (1, 2, 3)
        """

        # 根据plan中的sessions字段确定阶段
        for stage_info in global_plan:
            if not isinstance(stage_info, dict):
                continue

            sessions_range = stage_info.get("sessions", "") # 从sessions字段中找到
            stage_number = stage_info.get("stage_number", 1)

            # 解析sessions字段，如"第1-第2次", "第3–第6次", "第7–第7次"
            if isinstance(sessions_range, str):
                # 提取数字范围
                import re
                numbers = re.findall(r'\d+', sessions_range)
                if len(numbers) >= 2:
                    start_session = int(numbers[0])
                    end_session = int(numbers[1])

                    if start_session <= session_num <= end_session:
                        return stage_number
                elif len(numbers) == 1:
                    start_session = int(numbers[0])
                    end_session = int(numbers[0])
                    if start_session <= session_num <= end_session:
                        return stage_number
        
        return 3
                    
    def process_client(self, progress_data, filename):
        """根据已有进度，继续为单个来访者生成多轮对话"""
        history1 = [session for session in progress_data.get('sessions', [])]

        history = deepcopy(history1)    # 没有think的对话、summary、goals完整历史

        # 2. 在这个独立的副本上，使用修正后的逻辑进行清理操作
        think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)
        for session in history:
            dialogue_list = session.get('session_dialogue', [])
            if isinstance(dialogue_list, list):
                for turn in dialogue_list:
                    if isinstance(turn, dict) and turn.get('role') == 'Counselor' and 'text' in turn and turn['text']:
                        turn['text'] = think_pattern.sub('', turn['text'])

        session_num = len(history) + 1
        max_sessions = 10

        client_id = progress_data.get('client_id', filename.replace('.json', ''))
        logger.info(f"[FLOW] {client_id} - 开始处理第 {session_num} 轮咨询")
        


        while session_num <= max_sessions:
            logger.info(f"\n{'='*50}")
            logger.info(f"[SESSION] 第 {session_num} 轮咨询 - 来访者 {progress_data['client_id']}")
            logger.info(f"{'='*50}")

            client_info = progress_data.get('client_info', {})
            global_plan = progress_data.get('global_plan', [])

            logger.info("[GOALS] 步骤1: 生成咨询目标...")
            logger.info(f"[FLOW] {client_id} - 开始生成咨询目标")
            history_summary = [
                {
                    "session_number": s.get("session_number"),
                    "session_goals": s.get("session_goals"),
                    "session_summary": s.get("session_summary")
                }
                for s in history
            ]

            if session_num == 1 :
                current_stage = self._determine_stage_by_session_num(session_num, global_plan)
                logger.info(f"[STAGE] 当前治疗阶段: 第{current_stage}阶段")

                goals_key = 'goals_session1'

                # 3. 构建 plan_for_this_session
                plan_for_this_session = {} # 取第一个session的内容
                session_key = f"第1次_session_content"
                
                for stage in global_plan:
                    stage_content = stage.get('content')
                    if isinstance(stage_content, dict):
                        if session_key in stage_content:
                            plan_for_this_session = stage_content[session_key]
                            break # 找到后即退出循环


                unlocked_client_info = {}
                session_summaries = []
                # 4. 组装最终的 goals_input
                goals_input = {
                    "history": {
                        "session_summaries": session_summaries,
                        "unlocked_client_info": unlocked_client_info
                    },
                    "plan_for_this_session": plan_for_this_session,
                    "session_number": session_num,
                }
                
                # --- 结束修改 ---
                # 添加详细的调用前后日志
                logger.debug(f"[FLOW] - .*prompts\n\n {self.prompts[goals_key]}")
                logger.debug(f"[FLOW] - 第一个session的咨询目标生成的Input\n\n {goals_input}")

                goals_result = self.api_handler.call(self.prompts[goals_key], goals_input)
                

                if not goals_result:
                    logger.error(f"  ❌ 错误: 生成第 {session_num} 轮咨询目标失败，终止该来访者的处理。")
                    return False

                # logger.debug(f"[FLOW] - .*Output\n\n {goals_result}")
                if current_stage == 1 :
                    overall_stage = '问题概念化与目标设定'
                elif current_stage == 2 :
                    overall_stage = "核心认知与行为干预"
                else:
                    overall_stage = "巩固与复发预防"
                session_goals = {
                    "overall_stage": overall_stage,
                    "session_focus": goals_result.get("session_focus", "")
                }

            else:
                # 第二个session开始从summary中直接复制进来

                # 根据plan和session_num确定当前治疗阶段
                current_stage = self._determine_stage_by_session_num(session_num, global_plan)
                logger.info(f"[STAGE] 当前治疗阶段: 第{current_stage}阶段")

                # 从history_summary中获取最后一个summary的next_session_plan
                if not history_summary:
                    logger.error(f"  ❌ 错误: 第{session_num}轮没有历史summary，无法获取next_session_plan")
                    return False

                last_session = history_summary[-1]
                last_summary_obj = last_session.get('session_summary', {})
                print(last_session['session_number'])
                if not isinstance(last_summary_obj, dict):
                    logger.error(f"  ❌ 错误: 第{session_num}轮最后一个summary不是字典格式，无法获取next_session_plan")
                    return False

                goals_result = last_summary_obj.get('next_session_plan')
                if not goals_result:
                    logger.error(f"  ❌ 错误: 第{session_num}轮无法从历史summary中获取goals_result")
                    return False

                logger.info(f"[GOALS] 从历史summary中获取第{session_num}轮咨询目标")
                if current_stage == 1 :
                    overall_stage = '问题概念化与目标设定'
                elif current_stage == 2 :
                    overall_stage = "核心认知与行为干预"
                else:
                    overall_stage = "巩固与复发预防"
                session_goals = {
                    "overall_stage": overall_stage,
                    "session_focus": goals_result.get("session_focus", "")
                }
                # print("session_goals Output:\n",session_goals)
                # 构建unlocked_client_info (从 history_summary 列表的最后一个元素的 session_summary 字典中获取 'client_info_merge')
                unlocked_client_info = last_summary_obj.get('client_info_merge', {})

            # 生成bt技能（根据咨询目标选择合适的技能）
            logger.info("[SKILLS] 步骤1.5: 选择bt技能...")

            # <<<<<<< 修改：调用时传入 current_stage
            skills_result = self._generate_skills(goals_result, session_num, current_stage)
            

            if not skills_result:
                logger.error(f"[ERROR] 生成第 {session_num} 轮bt技能失败，终止该来访者的处理。")
                return False

            # 仅读取最后一个session的dialogue
            last_dialogues_concise = history[-1].get('session_dialogue', []) if history else []
            


            
            origin_dialogue = self._generate_dialogue(client_info, global_plan, history_summary, last_dialogues_concise, session_goals, skills_result, unlocked_client_info, session_num)

            if origin_dialogue is None:
                logger.error(f"[ERROR] 生成第 {session_num} 轮原始对话失败，终止该来访者的处理。")
                return False

            check_result = self._check_and_rewrite_dialogue(client_info, global_plan, history_summary, last_dialogues_concise, session_goals, skills_result, unlocked_client_info, session_num, origin_dialogue)

            if check_result is None:
                logger.error(f"[ERROR] 第 {session_num} 轮对话检查和重写失败，终止该来访者的处理。")
                return False

            # 分开接收evaluation和revised_dialogue
            evaluation_result = check_result.get('evaluation', {})
            revised_dialogue_result = check_result.get('revised_dialogue', {})
            output_dialogue = revised_dialogue_result

            if output_dialogue is None:
                logger.error(f"[ERROR] 重写后的对话为空，终止该来访者的处理。")
                return False

            # 保存origin_dialogue和check_result到文件
            self._save_session_dialogue_check(client_id, session_num, origin_dialogue, check_result)
            
            session_dialogue = output_dialogue.get("dialogue", [])

            think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)
            clean_dialogue = deepcopy(session_dialogue)
            for item in clean_dialogue:
                if item.get('role') == 'Counselor' and 'text' in item:
                    item['text'] = think_pattern.sub('', item['text'])

            session_summary = self._generate_summary(client_info, global_plan, history_summary, session_goals, clean_dialogue, session_num,unlocked_client_info)
            if session_summary is None: return False
            

            
            current_session = {
                "session_number": session_num,
                "session_goals": session_goals,
                "suggest_skills": skills_result,
                "session_dialogue": session_dialogue,
                "session_summary": session_summary,
                "client_info_last": session_summary['client_info_merge']
            }
            clean_session = {
                "session_number": session_num,
                "session_goals": session_goals,
                "session_dialogue": clean_dialogue,
                "session_summary": session_summary,
                "client_info_last": session_summary['client_info_merge']
            }


            progress_data['sessions'].append(current_session)
            history.append(clean_session)

            self.data_manager.save_progress(progress_data, filename)
            logger.info(f"[SAVE] 第 {session_num} 轮进度已保存")

            # 检查是否达到plan中的最大session数
            max_plan_session = self._get_max_session_from_plan(global_plan)
            if session_num >= max_plan_session:
                logger.info(f"[COMPLETE] 来访者 {progress_data['client_id']} 咨询流程完成（达到计划最大会话数 {max_plan_session}）")
                return True

            session_num += 1
        
        if session_num > max_sessions:
            logger.info(f"⚠️ 警告: 已达到最大会话次数 ({max_sessions})，自动终止该来访者的处理。")
        
        return True


    def _generate_dialogue(self, client_info, global_plan, history_summary, last_dialogue, goals_result, skills_result,unlocked_client_info, session_num):
        # 根据plan和session_num确定当前治疗阶段
        current_stage = self._determine_stage_by_session_num(session_num, global_plan)

        # 根据阶段选择合适的dialogue提示词
        dialogue_key = f'dialogue{current_stage}'
        if dialogue_key not in self.prompts:
            logger.warning(f"[WARN] 未找到dialogue提示词 {dialogue_key}，使用dialogue1")
            dialogue_key = 'dialogue1'
        
        re_session_summaries = []
        for item in history_summary:
            summary_obj_original = item.get('session_summary', {})
            
            # 创建一个新字典，包含 session_number
            final_entry = {"session_number": item.get("session_number")}

            if isinstance(summary_obj_original, dict):
                # 1. 复制 session_summary 字典中的所有内容
                summary_content_copy = summary_obj_original.copy()
                
                # 2. 安全地移除不需要的键 (使用 .pop(key, None) 避免KeyError)
                summary_content_copy.pop('client_info_get', None)
                summary_content_copy.pop('client_info_merge', None)
                
                # 3. 将剩余的字段合并到 final_entry 中
                final_entry.update(summary_content_copy)

            re_session_summaries.append(final_entry)



        if dialogue_key in self.prompts:
            logger.info("[DIALOGUE] 步骤2: 生成咨询对话...")
            dialogue_input = {"client_info": client_info, "unlocked_client_info":unlocked_client_info, "history_summary": re_session_summaries, "dialogue_history": last_dialogue, "session_goals": goals_result, "suggested_skills": skills_result}
            

            # 添加详细的调用前后日志
            logger.debug(f"[FLOW] - .*prompts\n\n {self.prompts[dialogue_key]}")
            logger.debug(f"[FLOW] - 咨询对话生成的Input\n\n {dialogue_input}")
            
            session_dialogue = self.api_handler.call(self.prompts[dialogue_key], dialogue_input)

            # logger.debug(f"[FLOW] - .*Output\n\n {session_dialogue}")

            if not session_dialogue:
                logger.error(f"[ERROR] 生成第 {session_num} 轮咨询对话失败。")
                return None
            logger.info("[SUCCESS] 咨询对话生成成功")
            return session_dialogue
        return {"dialogue": f"这是第{session_num}轮模拟对话 (prompt未加载)。"}

    def _check_and_rewrite_dialogue(self, client_info, global_plan, history_summary, last_dialogue, goals_result, skills_result, unlocked_client_info, session_num, draft_session_dialogue):
        """
        使用GPT-5 API对生成的对话进行检查和重写

        Args:
            client_info (dict): 来访者基本信息
            global_plan (dict): 全局治疗计划
            history_summary (list): 历史会话摘要
            last_dialogue (list): 最后一轮对话历史
            goals_result (dict): 当前会话目标
            skills_result (dict): bt技能结果
            unlocked_client_info (dict): 已解锁的来访者信息
            session_num (int): 当前会话次数
            draft_session_dialogue (dict): 初稿生成的对话数据

        Returns:
            dict: 重写后的对话数据，失败时返回None
        """
        check_remake_key = 'check_remake'

        if check_remake_key not in self.prompts:
            logger.warning(f"[WARN] 未找到check_remake提示词，跳过对话检查和重写")
            return draft_session_dialogue

        logger.info("[CHECK_REMAKE] 步骤2.5: 检查和重写咨询对话...")

        # 1. 构建第一次对话生成的历史消息
        current_stage = self._determine_stage_by_session_num(session_num, global_plan)
        dialogue_key = f'dialogue{current_stage}'

        re_session_summaries = []
        for item in history_summary:
            summary_obj_original = item.get('session_summary', {})
            
            # 创建一个新字典，包含 session_number
            final_entry = {"session_number": item.get("session_number")}

            if isinstance(summary_obj_original, dict):
                # 1. 复制 session_summary 字典中的所有内容
                summary_content_copy = summary_obj_original.copy()
                
                # 2. 安全地移除不需要的键 (使用 .pop(key, None) 避免KeyError)
                summary_content_copy.pop('client_info_get', None)
                summary_content_copy.pop('client_info_merge', None)
                
                # 3. 将剩余的字段合并到 final_entry 中
                final_entry.update(summary_content_copy)

            re_session_summaries.append(final_entry)


        # 构建dialogue_input (复用_generate_dialogue中的逻辑)
        dialogue_input = {
            "client_info": client_info,
            "unlocked_client_info": unlocked_client_info,
            "history_summary": re_session_summaries,
            "dialogue_history": last_dialogue,
            "session_goals": goals_result,
            "suggested_skills": skills_result
        }

        # 构建历史消息：将第一次对话生成的完整过程作为历史
        history_messages = [
            {"role": "user", "content": json.dumps(dialogue_input, ensure_ascii=False, indent=2)},
            {"role": "assistant", "content": json.dumps(draft_session_dialogue, ensure_ascii=False, indent=2)}
        ]

        # 2. 构建检查重写的输入数据（将check_remake提示词作为用户输入的一部分）
        check_remake_user_input = {
            "instruction": self.prompts[check_remake_key]
        }

        # 添加详细的调用前后日志
        logger.debug(f"[FLOW] - 对话生成的system prompt\n\n {self.prompts[dialogue_key][:200]}...")
        logger.debug(f"[FLOW] - 第一次对话生成的user input\n\n {json.dumps(dialogue_input, ensure_ascii=False, indent=2)[:500]}...")
        logger.debug(f"[FLOW] - check_remake指令\n\n {self.prompts[check_remake_key]}")
        logger.debug(f"[FLOW] - 对话检查和重写的完整Input\n\n {check_remake_user_input}")

        # 3. 使用带历史的API调用进行检查和重写
        # 保留原来的dialogue system prompt，将check_remake作为新的user input
        rewritten_dialogue = self.api_handler.call_with_history(
            self.prompts[dialogue_key],  # 使用原来的对话生成prompt作为system prompt
            check_remake_user_input,     # 将check_remake提示词和数据作为user input
            history_messages
        )

        # logger.debug(f"[FLOW] - check_remake Output\n\n {rewritten_dialogue}")

        if not rewritten_dialogue:
            logger.error(f"[ERROR] 第 {session_num} 轮对话检查和重写失败。")
            return None

        logger.info("[SUCCESS] 对话检查和重写成功")
        return rewritten_dialogue




    def _generate_summary(self, client_info, plan, history, session_goals, session_dialogue, session_num,unlocked_client_info):
        # 目前只有summary，如果后续有其他阶段的summary可以扩展
        summary_key = 'summary'

        if summary_key in self.prompts:
            logger.info("[SUMMARY] 步骤3: 生成咨询摘要...")
            summary_input = {"client_info": client_info, "unlocked_client_info":unlocked_client_info, "plan": plan, "history": history, "session_focus": session_goals, "session_dialogue": session_dialogue}

            # 添加详细的调用前后日志
            logger.debug(f"[FLOW] - .*prompts\n\n {self.prompts[summary_key]}")
            logger.debug(f"[FLOW] - 咨询摘要生成的Input\n\n {summary_input}")

            session_summary = self.api_handler.call(self.prompts[summary_key], summary_input)
            


            client_info_get = self._generate_get_client_info(session_num,session_dialogue)


            client_info_merged = self._generate_merge_client_info(unlocked_client_info, client_info_get, client_info, session_num)
            # 调用来访者信息合并方法


            # 调用下个session 的目标生成方法
            next_session_plan = self._generate_next_session_plan(history,session_summary,plan,session_num+1,client_info_merged)


            session_summary['client_info_get'] = client_info_get

            # 将合并后的信息存入session_summary
            session_summary['client_info_merge'] = client_info_merged
            session_summary['next_session_plan'] = next_session_plan
            # logger.debug(f"[FLOW] - .*Output\n\n {session_summary}")

            if not session_summary:
                logger.error(f"[ERROR] 生成第 {session_num} 轮咨询摘要失败。")
                return None
            logger.info("[SUCCESS] 咨询摘要生成成功")
            return session_summary
        return {"summary": f"这是第{session_num}轮模拟摘要 (prompt未加载)。"}
    


    def reformat_item(self, item_string):
        # (注意：添加了 self)
        try:
            number_str, text_part = item_string.split(':', 1)
            new_number = int(number_str) + 10000
            return f"{new_number}:{text_part}"
        except Exception:
            # 如果这个方法不需要访问 self 上的其他属性，
            # 也可以考虑方案二
            return item_string
    

    # <<<<<<< 修改：整个 _generate_skills 方法重写
    def _generate_skills(self, goals_result, session_num, current_stage):
        """
        根据咨询目标选择合适的bt技能
        (修改：现在会根据 current_stage 动态加载技能文件，并从中抽样)

        Args:
            goals_result (dict): 生成的咨询目标
            session_num (int): 当前会话次数 (用于日志)
            current_stage (int): 当前阶段 (1, 2, or 3) (用于加载文件)

        Returns:
            dict: 选择的bt技能结果，失败时返回None
        """
        if 'skills' not in self.prompts:
            logger.warning(f"[{session_num}] [WARN] 未找到skills提示词，跳过技能选择")
            return {"suggest_skills": "默认技能集合"}

        logger.info(f"[{session_num}] [SKILLS] 步骤1.5: 正在为 阶段 {current_stage} 选择bt技能...")
        

        skills_input = {
            "session_goals": goals_result
        }

        '''
        初始化只要传一个流派名列表进去
        筛的函数要传流派名（字符串），session goals（列表），阶段（int），和粗筛的元技能的数目（int），然后我会返回给你一个嵌套的列表就和白天说的一样

        '''

        # --- 新增逻辑：构建动态prompt ---
        original_prompt = self.prompts['skills']
        final_prompt = original_prompt # 默认使用原始prompt

        skill_library = SkillManager(sects=["bt"], versions=["v2"])

        # if current_stage == 1:
        #     stage = "阶段一：问题概念化与目标设定"
        # elif current_stage == 2:
        #     stage = "阶段二：核心认知与行为干预"
        # elif current_stage == 3:
        #     stage = "阶段三：巩固与复发预防"

        goals_1 = goals_result.get('session_focus')


        model_kwgs = {
                "api_key": "sk-ogOhHmD6PRSSKsx8Tch63KhIXlwKaofCJsh7VlJAkzw7nzmp",
                "base_url": "http://35.220.164.252:3888/v1/",
                "model_name": "gpt-5",
            }
        
    
        _, res = skill_library.corse_filter(
            sect = "bt",
            session_goals=goals_1,
            stage = current_stage,
            saved = True ,
            n = 20,
            model_kwgs = model_kwgs
        )

        # 移除每个技能字典中的parent_ids字段
        if isinstance(res, list):
            for meta_skill_dict in res:
                if isinstance(meta_skill_dict, dict) and 'micro_skills' in meta_skill_dict:
                    micro_skills = meta_skill_dict['micro_skills']
                    if isinstance(micro_skills, list):
                        for skill_dict in micro_skills:
                            if isinstance(skill_dict, dict) and 'parent_ids' in skill_dict:
                                del skill_dict['parent_ids']

        print(res) # [{},{}]

        if isinstance(res, dict):
                res = res['skill']
                print("数据类型是字典 (dict)，已提取。")

        elif isinstance(res, list):
            # 2. 如果是列表 (list)，就不处理
            print("数据类型是列表 (list)，不进行处理。")


        
        final_prompt = (
            f"{original_prompt}\n\n"
            f"技能列表库:{res}"
        )

        
        # # 为了避免日志过长，只打印prompt的开头部分
        logger.debug(f"[FLOW]  - bt技能选择的prompts\n\n {final_prompt}...")  
        logger.debug(f"[FLOW] - bt技能选择的Input\n\n {skills_input} ")
        
        # # 使用 final_prompt 调用API
        skills_result = self.api_handler.call(final_prompt, skills_input)
        # logger.debug(f"[FLOW] - .*Output\n\n {skills_result} ")


        if skills_result:
            logger.info(f"[{session_num}] [SUCCESS] bt技能选择成功")
            # 确保返回的是技能内容
            return skills_result.get('skill', skills_result) 
        else:
            logger.error(f"[{session_num}] [ERROR] 第 {session_num} 轮bt技能选择失败")
            return None
        

    def _generate_get_client_info(self, session_num,current_session_dialogue):
        """
        得到来访者档案信息
        """
        if 'client_get' not in self.prompts:
            logger.warning(f"[{session_num}] [WARN] 未找到client_merge提示词，跳过信息合并")
            return "错误"

        logger.info(f"[{session_num}] [MERGE] 步骤3.5: 合并来访者档案信息...")

        # 构建API调用输入
        get_input = {
            "session_number": session_num,
            "current_session_dialogue": current_session_dialogue,
        }

        # 添加详细的调用前后日志
        logger.debug(f"[FLOW] - client_info_get的prompts\n\n {self.prompts['client_get']}")
        logger.debug(f"[FLOW] - client_info_get的Input\n\n {get_input}")

        # 调用API进行合并
        get_result = self.api_handler.call(self.prompts['client_get'], get_input)

        # logger.debug(f"[FLOW] - client_info合并的Output\n\n {get_result}")

        if get_result and 'client_info_get' in get_result:
            logger.info(f"[{session_num}] [SUCCESS] 来访者档案信息get成功")
            return get_result['client_info_get']
        else:
            logger.error(f"[{session_num}] [ERROR] client_infoget失败")
            return "get失败"  # 返回原有信息作为fallback
        
    def _generate_merge_client_info(self, current_profile, client_info_last,global_profile, session_num):
        """
        合并来访者档案信息

        Args:
            current_profile (dict): 当前最新的client_info_merge
            client_info_last (dict): 从session_summary中提取的client_info_get
            session_num (int): 当前会话次数

        Returns:
            dict: 合并后的client_info_merged，失败时返回None
        """
        if 'client_merge' not in self.prompts:
            logger.warning(f"[{session_num}] [WARN] 未找到client_merge提示词，跳过信息合并")
            return current_profile

        logger.info(f"[{session_num}] [MERGE] 步骤3.5: 合并来访者档案信息...")

        # 构建API调用输入
        merge_input = {
            "history_profile": current_profile,
            "current_profile": client_info_last,
            "global_profile": global_profile,
            "session_number": session_num
        }

        # 添加详细的调用前后日志
        logger.debug(f"[FLOW] - client_info合并的prompts\n\n {self.prompts['client_merge']}")
        logger.debug(f"[FLOW] - client_info合并的Input\n\n {merge_input}")

        # 调用API进行合并
        merge_result = self.api_handler.call(self.prompts['client_merge'], merge_input)

        # logger.debug(f"[FLOW] - client_info合并的Output\n\n {merge_result}")

        if merge_result and 'client_info_merge' in merge_result:
            logger.info(f"[{session_num}] [SUCCESS] 来访者档案信息合并成功")
            return merge_result['client_info_merge']
        else:
            logger.error(f"[{session_num}] [ERROR] client_info合并失败")
            return current_profile  # 返回原有信息作为fallback
        
    def _generate_next_session_plan(self,history_summary,summary,global_plan,session_num,client_info_last):
        current_stage = self._determine_stage_by_session_num(session_num, global_plan)
        logger.info(f"[STAGE] 当前session为{session_num} ,治疗阶段: 第{current_stage}阶段,global_plan是{global_plan}")

        # 1. 构建 history.session_summaries(修正：提取 session_summary 对象中除了 'client_info_get' 和 'client_info_merge' 之外的所有字段)
        new_session_summaries = []
        for item in history_summary:
            summary_obj_original = item.get('session_summary', {})
            
            # 创建一个新字典，包含 session_number
            final_entry = {"session_number": item.get("session_number")}

            if isinstance(summary_obj_original, dict):
                # 1. 复制 session_summary 字典中的所有内容
                summary_content_copy = summary_obj_original.copy()
                
                # 2. 安全地移除不需要的键 (使用 .pop(key, None) 避免KeyError)
                summary_content_copy.pop('client_info_get', None)
                summary_content_copy.pop('client_info_merge', None)
                
                # 3. 将剩余的字段合并到 final_entry 中
                final_entry.update(summary_content_copy)

            new_session_summaries.append(final_entry)

        goals_key = f'goals{current_stage}'
        if goals_key not in self.prompts:
            logger.warning(f"[WARN] 未找到goals提示词 {goals_key}，使用goals")
            goals_key = f'goals'


        plan_for_this_session = {} # 默认为空
        session_key = f"第{session_num}次_session_content"
        
        for stage in global_plan:
            # 检查 stage['content'] 是否是一个字典
            stage_content = stage.get('content')
            if isinstance(stage_content, dict):
                # 检查 'session_key' 是否存在于 'content' 字典中
                if session_key in stage_content:
                    plan_for_this_session = stage_content[session_key]
                    break # 找到后即退出循环
        
        goals_input = {
                "history_summary": {
                    "session_summaries": new_session_summaries,
                    "last_summary":   summary             
                },
                "client_info_last":client_info_last,
                "plan_for_this_session": plan_for_this_session,
                "session_number": session_num,
            }
        
        goals_result = self.api_handler.call(self.prompts[goals_key], goals_input)

        # logger.debug(f"[FLOW] - .*Output\n\n {goals_result}")
        if current_stage == 1 :
            overall_stage = '问题概念化与目标设定'
        elif current_stage == 2 :
            overall_stage = "核心认知与行为干预"
        else:
            overall_stage = "巩固与复发预防"
        session_goals = {
            "overall_stage": overall_stage,
            "session_focus": goals_result.get("session_focus", "")
        }
        return session_goals

    def _save_session_dialogue_check(self, client_id, session_num, origin_dialogue, check_result):
        """
        保存原始对话和检查重写结果到文件

        Args:
            client_id (str): 来访者ID
            session_num (int): 会话次数
            origin_dialogue (dict): 原始生成的对话
            check_result (dict): 检查和重写结果
        """
        try:
            # 创建基于user_id的目录结构
            base_output_dir = '/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/unintake/dialogue_check_remake'
            user_dir = os.path.join(base_output_dir, str(client_id))
            os.makedirs(user_dir, exist_ok=True)

            # 构建文件名，格式为: user_id_session_N.json
            filename = f"{client_id}_session_{session_num}.json"
            file_path = os.path.join(user_dir, filename)

            # 准备要保存的数据
            save_data = {
                "client_id": client_id,
                "session_number": session_num,
                "origin_dialogue": origin_dialogue,
                "check_result": check_result,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            # 保存到文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4, ensure_ascii=False)

            logger.info(f"[SAVE] 对话检查结果已保存: {file_path}")

        except Exception as e:
            logger.error(f"[ERROR] 保存对话检查结果失败: {e}")





# --- 5. 主执行函数 (Main Execution) ---

# <<<<<<< 新增：为多线程设计的独立工作单元函数
def process_file_worker(file_path, data_manager, session_generator):
    """
    处理单个文件的单元任务，专为多线程设计。
    """
    file_name = os.path.basename(file_path)
    client_id = file_name.replace('.json', '')  # 从文件名提取客户ID
    logger.info(f"\n{'='*60}")
    logger.info(f"[START] 开始处理文件: {file_name}")
    logger.info(f"[FLOW] {client_id} - 开始完整数据生成流程")
    logger.info(f"{'='*60}")
    
    client_data = data_manager.load_client_data(file_path)
    if not client_data:
        # load_client_data 内部已经打印了错误，这里直接返回
        return

    # 1. 加载或初始化进度
    progress_data = data_manager.load_or_initialize_progress(client_data, file_name)

    # 2. 运行处理流程
    is_successful = session_generator.process_client(progress_data, file_name)
    
    # 3. 如果流程成功跑完，则记录到最终完成日志
    if is_successful:
        data_manager.log_completion(file_name)
        logger.info(f"[FLOW] {client_id} - 完整数据生成流程完成")
    else:
        logger.error(f"[ERROR] 文件 {file_name} 处理中途失败，已保存部分进度，将在下次运行时重试。")

def main():
    """主函数：加载数据，管理进度，并使用多线程调用处理流程""" # <<<<<<< 修改
    cfg = Config()
    
    if "YOUR_API" in cfg.API_KEY or "YOUR_API" in cfg.BASE_URL:
        logger.info("🛑 错误: 请在脚本的Config类中设置您的 API_KEY 和 BASE_URL。")
        return

    data_manager = DataManager(cfg)
    
    prompts = data_manager.load_prompts()



    try:
        api_handler = APIHandler(cfg)
        # <<<<<<< 修改：初始化 SessionGenerator 时移除 all_skills_data
        session_generator = SessionGenerator(api_handler, prompts, data_manager)
        logger.info("[INIT] API客户端和会话生成器初始化成功")

    except ValueError as e:
        logger.info(f"🛑 {e}")
        return

    files_to_process = data_manager.get_files_to_process()
    if not files_to_process:
        logger.info("✅ 所有文件均已处理完毕。")
        return

    # 根据线程数选择处理方式
    if cfg.MAX_WORKERS == 1:
        # 单线程模式：直接调用，避免进度条重复显示
        test_file = files_to_process[0]
        logger.info(f"\n{'='*60}")
        logger.info(f"[TEST] 单线程模式: 处理单个文件")
        logger.info(f"[SELECT] 选择文件: {os.path.basename(test_file)}")
        logger.info(f"{'='*60}")

        try:
            process_file_worker(test_file, data_manager, session_generator)
        except Exception as exc:
            logger.error(f"‼️ 文件 {os.path.basename(test_file)} 处理过程中发生严重错误: {exc}")
    else:
        # 多线程模式：使用线程池

        # 测试单文件
        # print(files_to_process)
        # test_file = files_to_process[0]
        # print(test_file)
        
        # files_to_process = ["/mnt/shared-storage-user/cl4mind/panqianjun/make_data/C_other_school/bt/unintake/test/client_info/1.json",
                            # ]
        # print(files_to_process)
        # logger.info(f"\n{'='*60}")
        # logger.info(f"[TEST] 多线程模式: 处理单个文件")
        # logger.info(f"[SELECT] 选择文件: {os.path.basename(test_file)}")
        # logger.info(f"{'='*60}")


        # 处理多文件
        with ThreadPoolExecutor(max_workers=cfg.MAX_WORKERS) as executor:
            # 提交所有任务，并创建一个从future到文件路径的映射
            future_to_file = {
                executor.submit(process_file_worker, file_path, data_manager, session_generator): file_path
                for file_path in files_to_process
            }

            # 使用tqdm来显示总体进度，并在任务完成时处理结果
            progress_bar = tqdm(as_completed(future_to_file), total=len(files_to_process), desc="🚀 总体进度")
            for future in progress_bar:
                file_path = future_to_file[future]
                try:
                    # 获取任务结果。如果任务中发生异常，这里会重新抛出
                    future.result()
                except Exception as exc:
                    # 捕获在worker函数中未捕获的严重错误
                    logger.error(f"‼️ 文件 {os.path.basename(file_path)} 的处理线程中发生严重错误: {exc}")

    logger.info("\n" + "="*50)
    logger.info("[FINISH] 所有任务处理完成!")
    logger.info("="*50)

if __name__ == "__main__":
    main()