#pragma once

#include <ns3/rtt-estimator.h>
#include <functional>

namespace lab
{
class RttObserver : public ns3::RttMeanDeviation
{
  public:
    static ns3::TypeId GetTypeId()
    {
        static ns3::TypeId tid = ns3::TypeId("ns3::LabRttObserver")
            .SetParent<ns3::RttMeanDeviation>().AddConstructor<RttObserver>();
        return tid;
    }

    std::function<void(ns3::Time)> observer;

    void Measurement(ns3::Time value) override
    {
        ns3::RttMeanDeviation::Measurement(value);
        // 记录 TCP 实际交给估计器的样本，包括连续相等的 RTT。
        if (observer) observer(value);
    }

    ns3::Ptr<ns3::RttEstimator> Copy() const override
    {
        return ns3::CopyObject<RttObserver>(this);
    }
};
}
