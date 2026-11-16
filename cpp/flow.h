#pragma once

#include "controllers.h"
#include "support.h"
#include <ns3/applications-module.h>
#include <ns3/internet-module.h>

#include <deque>
#include <limits>
#include <vector>

namespace lab
{
struct Flow
{
    int id;
    Json config;
    Journal& journal;
    ns3::Ptr<ns3::Node> sender, receiver;
    ns3::Ipv4Address destination;
    ns3::Ptr<ns3::TcpSocketBase> socket;
    ns3::Ptr<ns3::TcpSocketState> state;
    ns3::Ptr<TcpGlmReno> adaptive;
    ns3::Ptr<ns3::PacketSink> sink;
    uint64_t sent{0}, received{0}, txBytes{0}, retransBytes{0}, acked{0};
    uint64_t previousTx{0}, previousRetrans{0}, previousAcked{0};
    uint32_t ackMark{1};
    bool connected{false}, producing{false}, packetEvents;
    double actualStart{0}, minRtt{std::numeric_limits<double>::infinity()};
    double beta{0.5}, activatedAt{0};
    Json lastThresholdTime = nullptr;
    Json completedAt = nullptr;
    std::string decisionId{"initial"};
    std::vector<double> rttSamples;
    std::deque<Json> history;
    uint64_t window{0};

    Flow(int number, Json settings, Journal& log, bool packets);
    void Start();
    void Stop();
    bool Active() const;
    Json Observe();
    void Activate(Json action);
    void Receive(ns3::Ptr<const ns3::Packet>, const ns3::Address&, const ns3::Address&);

  private:
    void Event(const std::string&, Json data = Json::object());
    void CheckComplete();
    void Connected(ns3::Ptr<ns3::Socket>);
    void Failed(ns3::Ptr<ns3::Socket>);
    void Available(ns3::Ptr<ns3::Socket>, uint32_t);
    void Send();
    void Cwnd(uint32_t, uint32_t);
    void Threshold(uint32_t, uint32_t);
    void Congestion(ns3::TcpSocketState::TcpCongState_t, ns3::TcpSocketState::TcpCongState_t);
    void Timeout(ns3::Time, ns3::Time);
    void Tx(ns3::Ptr<const ns3::Packet>, const ns3::TcpHeader&, ns3::Ptr<const ns3::TcpSocketBase>);
    void Rx(ns3::Ptr<const ns3::Packet>, const ns3::TcpHeader&, ns3::Ptr<const ns3::TcpSocketBase>);
    void Retransmit(ns3::Ptr<const ns3::Packet>, const ns3::TcpHeader&, const ns3::Address&,
                    const ns3::Address&, ns3::Ptr<const ns3::TcpSocketBase>);
    void RttMeasured(ns3::Time);
    void Computed(uint32_t, uint32_t, uint32_t);
};
}
