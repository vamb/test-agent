from __future__ import annotations

import re
from dataclasses import dataclass

from apps.api.settings import AppSettings
from agent.runtime.recorder import AgentRunRecorder
from tools.historical.postgres_repository import PostgresHistoricalEventRepository
from tools.historical.repository import HistoricalEventRepository
from tools.historical.service import HistoricalQueryService


@dataclass(frozen=True)
class AgentStep:
    tool_name: str
    tool_arguments: dict
    observation: dict


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    steps: list[AgentStep]
    run_id: str | None = None


class SimpleHistoricalAgent:
    """A deterministic MVP agent for validating tools before model integration."""

    def __init__(
        self,
        service: HistoricalQueryService,
        recorder: AgentRunRecorder | None = None,
    ) -> None:
        self.service = service
        self.recorder = recorder

    @classmethod
    def from_sample_data(cls) -> "SimpleHistoricalAgent":
        repository = HistoricalEventRepository.from_default_sample()
        return cls(HistoricalQueryService(repository))

    @classmethod
    def from_postgres(cls, record_runs: bool = True) -> "SimpleHistoricalAgent":
        settings = AppSettings.from_env().postgres
        repository = PostgresHistoricalEventRepository(settings)
        recorder = AgentRunRecorder(settings) if record_runs else None
        return cls(HistoricalQueryService(repository), recorder=recorder)

    def run(self, user_input: str) -> AgentResponse:
        recorded_run = self.recorder.start_run(user_input) if self.recorder else None
        try:
            response = self._run_without_recording(user_input, recorded_run.run_id if recorded_run else None)
        except Exception as exc:
            if self.recorder and recorded_run:
                self.recorder.fail_run(recorded_run.run_id, str(exc))
            raise

        if self.recorder and recorded_run:
            self.recorder.finish_run(recorded_run.run_id, response.answer)
        return response

    def _run_without_recording(
        self, user_input: str, run_id: str | None = None
    ) -> AgentResponse:
        years = [int(item) for item in re.findall(r"-?\d{3,4}", user_input)]
        steps: list[AgentStep] = []

        relation_event_id = self._infer_known_event_id(user_input)
        if relation_event_id and self._asks_for_relation(user_input):
            years_for_relation = [int(item) for item in re.findall(r"-?\d{3,4}", user_input)]
            detail_args = {"event_id": relation_event_id}
            detail = self.service.get_event_detail(relation_event_id)
            detail_step = AgentStep("get_event_detail", detail_args, detail)
            self._record_step(run_id, len(steps), detail_step)
            steps.append(detail_step)

            if detail.get("found"):
                event_year = years_for_relation[0] if years_for_relation else detail["event"]["start_year"]
                year_args = {
                    "year": event_year,
                    "regions": self._infer_regions(user_input) or None,
                    "nearby_window": 10,
                }
                year_observation = self.service.search_events_by_year(**year_args)
                year_step = AgentStep("search_events_by_year", year_args, year_observation)
                self._record_step(run_id, len(steps), year_step)
                steps.append(year_step)

            relation_args = {"event_id": relation_event_id}
            relations = self.service.find_related_events(relation_event_id)
            relation_step = AgentStep("find_related_events", relation_args, relations)
            self._record_step(run_id, len(steps), relation_step)
            steps.append(relation_step)
            return AgentResponse(
                self._format_relation_result(detail, relations),
                steps,
                run_id=run_id,
            )

        if len(years) >= 2:
            start_year, end_year = min(years[0], years[1]), max(years[0], years[1])
            regions = self._infer_regions(user_input)
            if not regions and self._asks_for_eurasian_context(user_input):
                regions = ["东亚", "中东", "中亚", "西欧"]
            range_args = {
                "start_year": start_year,
                "end_year": end_year,
                "regions": regions or None,
            }
            range_observation = self.service.search_events_by_range(**range_args)
            range_step = AgentStep("search_events_by_range", range_args, range_observation)
            self._record_step(run_id, len(steps), range_step)
            steps.append(range_step)

            args = {
                "start_year": start_year,
                "end_year": end_year,
                "regions": regions or None,
            }
            observation = self.service.compare_regions(**args)
            step = AgentStep("compare_regions", args, observation)
            self._record_step(run_id, len(steps), step)
            steps.append(step)
            return AgentResponse(self._format_comparison(observation), steps, run_id=run_id)

        if years:
            year = years[0]
            regions = self._infer_regions(user_input)
            nearby_window = 10 if self._asks_for_contemporary_context(user_input) else 0
            args = {
                "year": year,
                "regions": regions or None,
                "nearby_window": nearby_window,
            }
            observation = self.service.search_events_by_year(**args)
            step = AgentStep("search_events_by_year", args, observation)
            self._record_step(run_id, len(steps), step)
            steps.append(step)
            return AgentResponse(self._format_year_result(observation), steps, run_id=run_id)

        args = {"start_year": 600, "end_year": 900, "regions": None}
        observation = self.service.search_events_by_range(**args)
        step = AgentStep("search_events_by_range", args, observation)
        self._record_step(run_id, len(steps), step)
        steps.append(step)
        return AgentResponse(self._format_range_result(observation), steps, run_id=run_id)

    def _record_step(self, run_id: str | None, step_index: int, step: AgentStep) -> None:
        if self.recorder and run_id:
            self.recorder.record_tool_step(
                run_id=run_id,
                step_index=step_index,
                tool_name=step.tool_name,
                tool_arguments=step.tool_arguments,
                tool_result=step.observation,
            )

    def _infer_regions(self, text: str) -> list[str]:
        region_keywords = {
            "东亚": ["东亚", "中国", "日本", "唐朝", "隋朝"],
            "中东": ["中东", "阿拉伯", "伊斯兰", "阿拔斯"],
            "中亚": ["中亚", "怛罗斯"],
            "西欧": ["西欧", "欧洲", "法兰克", "查理曼"],
        }
        regions: list[str] = []
        for region, keywords in region_keywords.items():
            if any(keyword in text for keyword in keywords):
                regions.append(region)
        return regions

    def _asks_for_contemporary_context(self, text: str) -> bool:
        keywords = ["同时", "同期", "同一时期", "发生时", "背景", "横向"]
        return any(keyword in text for keyword in keywords) or ("发生" in text and "时" in text)

    def _asks_for_eurasian_context(self, text: str) -> bool:
        keywords = ["欧亚", "世界", "各地区", "各国", "对照表", "横向", "比较", "对比"]
        return any(keyword in text for keyword in keywords)

    def _asks_for_relation(self, text: str) -> bool:
        keywords = ["关系", "关联", "影响", "因果", "有关"]
        return any(keyword in text for keyword in keywords)

    def _infer_known_event_id(self, text: str) -> str | None:
        known_titles = ["怛罗斯之战", "安史之乱", "大化改新", "阿拔斯王朝", "唐朝建立"]
        for title in known_titles:
            if title in text:
                search_result = self.service.search_events_by_range(600, 900, limit=100)
                for event in search_result["events"]:
                    if title in event["title"] or event["title"] in title:
                        return event["id"]
        return None

    def _format_year_result(self, observation: dict) -> str:
        events = observation["events"]
        if not events:
            return f"当前数据集中没有找到 {observation['year']} 年的相关事件。"

        if observation.get("nearby_window", 0):
            lines = [
                f"{observation['year']} 年前后 {observation['nearby_window']} 年历史事件对照："
            ]
        else:
            lines = [f"{observation['year']} 年历史事件对照："]
        for event in events:
            lines.append(
                f"- {event['region']} / {event['polity']}：{event['title']}。{event['summary']}"
            )
        lines.append("说明：以上为同期事件；请区分同期与因果，是否存在因果关系需要进一步查看来源和事件关系。")
        return "\n".join(lines)

    def _format_range_result(self, observation: dict) -> str:
        events = observation["events"]
        if not events:
            return (
                f"当前数据集中没有找到 {observation['start_year']}-"
                f"{observation['end_year']} 年的相关事件。"
            )

        lines = [f"{observation['start_year']}-{observation['end_year']} 年历史事件："]
        for event in events:
            lines.append(
                f"- {event['start_year']}-{event.get('end_year') or event['start_year']} "
                f"{event['region']} / {event['polity']}：{event['title']}"
            )
        return "\n".join(lines)

    def _format_comparison(self, observation: dict) -> str:
        rows = observation["rows"]
        if not rows:
            return (
                f"当前数据集中没有找到 {observation['start_year']}-"
                f"{observation['end_year']} 年的对照事件。"
            )

        lines = [f"{observation['start_year']}-{observation['end_year']} 年中国与欧亚地区横向对照表："]
        for row in rows:
            title_list = "；".join(event["title"] for event in row["events"])
            lines.append(f"- {row['region']}：{title_list}")
        lines.append("分析提示：横向对照先展示同一时期背景，因果或影响关系需要单独验证。")
        return "\n".join(lines)

    def _format_relation_result(self, detail: dict, relations: dict) -> str:
        if not detail.get("found"):
            return "当前数据集中没有找到该事件，无法分析关系。"

        event = detail["event"]
        lines = [
            f"{event['title']}关系分析：",
            f"- 事件背景：{event['summary']}",
        ]
        relation_items = relations.get("relations", [])
        if not relation_items:
            lines.append("- 已知关系：当前数据库没有记录明确关系。")
        else:
            lines.append("- 已知关系：")
            for relation in relation_items:
                other_title = (
                    relation["target_title"]
                    if relation["source_event_id"] == event["id"]
                    else relation["source_title"]
                )
                lines.append(
                    f"  - {relation['relation_type']} / {other_title}："
                    f"{relation['explanation']} 证据强弱：{relation['confidence']}"
                )
        lines.append("说明：同期不等于因果；关系分析需要看 relation_type、confidence 和来源证据。")
        return "\n".join(lines)


if __name__ == "__main__":
    agent = SimpleHistoricalAgent.from_postgres(record_runs=True)
    response = agent.run("755年中国发生安史之乱时，中东和中亚发生了什么？")
    print(response.answer)
    if response.run_id:
        print(f"\nrun_id: {response.run_id}")
