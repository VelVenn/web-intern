#include "experiment.h"

#include <iostream>

namespace lab
{
using namespace ns3;

Experiment::Experiment(Json settings, fs::path path)
    : config(std::move(settings)), directory(std::move(path)), journal(directory),
      rate(static_cast<uint64_t>(config.at("rate_mbps").get<double>() * 1000000)),
      end(config.at("end_s")) {}

void Experiment::Decision(Flow* flow)
{
    if (!flow->socket || !flow->Active() || SecondsNow() >= end) return;
    Json observation = flow->Observe();
    std::string id = std::to_string(flow->id) + "-" + std::to_string(flow->window);
    observation["decision_id"] = id;
    journal.Write("observation", observation);
    if (flow->config.at("algorithm") == "glm")
    {
        std::cout << Json({{"protocol", 1}, {"type", "observation"},
            {"observation", observation}}).dump() << std::endl;
        std::string line;
        Require(static_cast<bool>(std::getline(std::cin, line)), "controller pipe closed");
        auto response = Json::parse(line);
        Require(response.at("protocol") == 1 && response.at("type") == "action", "invalid controller message");
        auto action = response.at("action");
        Require(action.at("decision_id") == id, "decision ID mismatch");
        // 先安排参数启用，再安排下一次观测，保证相同时间的事件顺序。
        Simulator::Schedule(Seconds(config.at("decision_delay_s").get<double>()), &Flow::Activate, flow, action);
    }
    if (SecondsNow() + 1 < end) Simulator::Schedule(Seconds(1), &Experiment::Decision, this, flow);
}

void Experiment::Sample()
{
    for (const auto& flow : flows)
    {
        uint32_t cwnd = flow->state ? flow->state->m_cWnd.Get() : 0;
        uint32_t threshold = flow->state ? flow->state->m_ssThresh.Get() : 0;
        double srtt = flow->state ? flow->state->m_srtt.Get().GetSeconds() * 1000 : 0;
        journal.samples << SecondsNow() << ',' << flow->id << ',' << flow->Active() << ','
            << flow->received << ',' << flow->sent << ',' << flow->txBytes << ','
            << flow->retransBytes << ',' << flow->acked << ',' << cwnd << ','
            << threshold << ',' << srtt << ',' << flow->beta << '\n';
    }
    double next = ++sampleNumber * config.at("sample_s").get<double>();
    if (next < end) Simulator::Schedule(Seconds(next - SecondsNow()), &Experiment::Sample, this);
}

void Experiment::Run()
{
    Build();
    std::cout << Json({{"protocol", 1}, {"type", "ready"}, {"ns3", "3.49"},
        {"compiler", LAB_COMPILER}}).dump() << std::endl;
    Simulator::Stop(Seconds(end));
    Simulator::Run();
    Json result = {{"flows", Json::array()}, {"queues", Json::array()},
        {"error_checks", error->checks}, {"error_drops", error->drops}};
    for (auto& f : flows)
    {
        Require(f->received <= f->sent, "receiver exceeds application bytes");
        result["flows"].push_back({{"flow", f->id}, {"algorithm", f->config.at("algorithm")},
            {"sent_bytes", f->sent}, {"received_bytes", f->received},
            {"acked_bytes", f->acked}, {"tx_bytes", f->txBytes}, {"retrans_bytes", f->retransBytes},
            {"pending_bytes", f->sent - f->received}, {"completed_at_s", f->completedAt},
            {"start_s", f->actualStart}, {"stop_s", f->config.at("stop_s")}});
    }
    for (auto& q : queues) result["queues"].push_back({{"queue", q->name},
        {"enqueued", q->arrivals}, {"dropped", q->drops}, {"pending_uids", q->entered.size()}});
    std::ofstream output(directory / "network.json");
    output.exceptions(std::ios::badbit | std::ios::failbit);
    output << result.dump(2) << '\n';
    journal.events.flush();
    journal.samples.flush();
    std::cout << Json({{"protocol", 1}, {"type", "complete"},
        {"time_s", SecondsNow()}}).dump() << std::endl;
    Simulator::Destroy();
}

void RunExperiment(Json config, const fs::path& directory)
{
    Experiment experiment(std::move(config), directory);
    experiment.Run();
}
}
