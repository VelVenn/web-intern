#pragma once

#include "support.h"
#include <ns3/network-module.h>
#include <ns3/traffic-control-module.h>

#include <deque>
#include <map>

namespace lab
{
int DeviceFlow(ns3::Ptr<const ns3::Packet> packet);

class ObservedError : public ns3::ErrorModel
{
  public:
    static ns3::TypeId GetTypeId();
    ns3::Ptr<ns3::ErrorModel> model;
    Journal* journal{nullptr};
    uint64_t checks{0}, drops{0};

  private:
    bool DoCorrupt(ns3::Ptr<ns3::Packet>) override;
    void DoReset() override;
};

struct QueueMonitor
{
    Journal& journal;
    std::string name;
    uint64_t arrivals{0}, drops{0};
    std::map<uint64_t, std::deque<double>> entered;

    QueueMonitor(Journal& log, std::string label);
    void DiscEnqueue(ns3::Ptr<const ns3::QueueDiscItem>);
    void DiscDequeue(ns3::Ptr<const ns3::QueueDiscItem>);
    void DiscDrop(ns3::Ptr<const ns3::QueueDiscItem>, const char*);
    void DeviceEnqueue(ns3::Ptr<const ns3::Packet>);
    void DeviceDequeue(ns3::Ptr<const ns3::Packet>);
    void DeviceDrop(ns3::Ptr<const ns3::Packet>);

  private:
    void Enter(uint64_t);
    double Leave(uint64_t);
};
}
