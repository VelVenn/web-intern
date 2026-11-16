#pragma once

#include <ns3/tcp-linux-reno.h>
#include <ns3/tcp-cubic.h>
#include <ns3/tcp-socket-state.h>

#include <functional>

namespace lab
{
using ThresholdObserver = std::function<void(uint32_t, uint32_t, uint32_t)>;

// 观测层保持 ns-3 原有的窗口增长和阈值算法。
class ObservedReno : public ns3::TcpLinuxReno
{
  public:
    static ns3::TypeId GetTypeId();
    ns3::Ptr<ns3::TcpSocketState> state;
    ThresholdObserver thresholdObserver;
    void Init(ns3::Ptr<ns3::TcpSocketState> tcb) override;
    uint32_t GetSsThresh(ns3::Ptr<const ns3::TcpSocketState>, uint32_t) override;
    ns3::Ptr<ns3::TcpCongestionOps> Fork() override;
};

class ObservedCubic : public ns3::TcpCubic
{
  public:
    static ns3::TypeId GetTypeId();
    ns3::Ptr<ns3::TcpSocketState> state;
    ThresholdObserver thresholdObserver;
    void Init(ns3::Ptr<ns3::TcpSocketState> tcb) override;
    uint32_t GetSsThresh(ns3::Ptr<const ns3::TcpSocketState>, uint32_t) override;
    ns3::Ptr<ns3::TcpCongestionOps> Fork() override;
};

class TcpGlmReno : public ObservedReno
{
  public:
    static ns3::TypeId GetTypeId();
    double beta{0.5};
    double initialBeta{0.5};
    std::string GetName() const override;
    uint32_t GetSsThresh(ns3::Ptr<const ns3::TcpSocketState>, uint32_t) override;
    ns3::Ptr<ns3::TcpCongestionOps> Fork() override;
};
}
