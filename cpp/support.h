#pragma once

#include <ns3/core-module.h>
#include <nlohmann/json.hpp>

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace lab
{
using Json = nlohmann::json;
namespace fs = std::filesystem;

inline void Require(bool value, const std::string& message)
{
    if (!value) throw std::runtime_error(message);
}

inline double SecondsNow() { return ns3::Simulator::Now().GetSeconds(); }

class Journal
{
  public:
    std::ofstream events;
    std::ofstream samples;

    explicit Journal(const fs::path& dir)
    {
        events.exceptions(std::ios::badbit | std::ios::failbit);
        samples.exceptions(std::ios::badbit | std::ios::failbit);
        events.open(dir / "events.jsonl");
        samples.open(dir / "samples.csv");
        samples << "time_s,flow,active,received_bytes,sent_bytes,tx_bytes,retrans_bytes,acked_bytes,cwnd_bytes,ssthresh_bytes,srtt_ms,beta\n";
        samples.precision(17);
    }

    void Write(const std::string& type, Json data = Json::object())
    {
        data["type"] = type;
        data["time_s"] = SecondsNow();
        events << data.dump() << '\n';
    }
};

void RunExperiment(Json config, const fs::path& directory);
}
