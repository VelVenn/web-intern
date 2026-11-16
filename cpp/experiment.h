#pragma once

#include "flow.h"
#include "network-monitor.h"
#include <ns3/point-to-point-module.h>

#include <memory>

namespace lab
{
class Experiment
{
  public:
    Experiment(Json settings, fs::path path);
    void Run();

  private:
    Json config;
    fs::path directory;
    Journal journal;
    std::vector<std::unique_ptr<Flow>> flows;
    std::vector<std::unique_ptr<QueueMonitor>> queues;
    ns3::Ptr<ObservedError> error;
    ns3::NetDeviceContainer bottleneck;
    ns3::DataRate rate;
    double end;
    uint64_t sampleNumber{0};

    void Build();
    void Monitor(ns3::Ptr<ns3::NetDevice>, ns3::Ptr<ns3::QueueDisc>, unsigned);
    void LinkTx(unsigned, ns3::Ptr<const ns3::Packet>);
    void Decision(Flow*);
    void Sample();
};
}
