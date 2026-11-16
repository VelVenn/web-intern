#include "flow.h"
#include "rtt-observer.h"

#include <algorithm>
#include <cmath>
#include <numeric>

namespace lab
{
using namespace ns3;

Flow::Flow(int number, Json settings, Journal& log, bool packets)
    : id(number), config(std::move(settings)), journal(log), packetEvents(packets) {}

void Flow::Event(const std::string& type, Json data)
{
    data["flow"] = id;
    journal.Write(type, std::move(data));
}

void Flow::Receive(Ptr<const Packet> packet, const Address&, const Address&)
{
    received += packet->GetSize();
    Event("receive", {{"bytes", packet->GetSize()}, {"total", received}});
    CheckComplete();
}

void Flow::CheckComplete()
{
    if (!producing && connected && received == sent && completedAt.is_null())
    {
        completedAt = SecondsNow();
        Event("flow_complete", {{"bytes", received}});
    }
}

void Flow::Connected(Ptr<Socket>)
{
    connected = true;
    Event("connected");
    Send();
}

void Flow::Failed(Ptr<Socket>) { throw std::runtime_error("TCP connection failed"); }
void Flow::Available(Ptr<Socket>, uint32_t) { Send(); }

void Flow::Send()
{
    while (producing && connected && socket->GetTxAvailable() > 0)
    {
        uint32_t size = std::min(1448U, socket->GetTxAvailable());
        int accepted = socket->Send(Create<Packet>(size), 0);
        Require(accepted > 0, "TCP Send failed with available send buffer");
        sent += static_cast<uint32_t>(accepted);
    }
}

void Flow::Stop()
{
    producing = false;
    Event("source_stopped", {{"submitted_bytes", sent}});
    CheckComplete();
}

void Flow::Cwnd(uint32_t old, uint32_t value)
{
    Event("cwnd", {{"old", old}, {"value", value},
                   {"ssthresh", static_cast<uint32_t>(state->m_ssThresh)}});
}

void Flow::Threshold(uint32_t old, uint32_t value)
{
    Event("ssthresh", {{"old", old}, {"value", value}});
}

void Flow::Congestion(TcpSocketState::TcpCongState_t old, TcpSocketState::TcpCongState_t value)
{
    Event("congestion", {{"old", static_cast<int>(old)}, {"value", static_cast<int>(value)},
        {"name", TcpSocketState::TcpCongStateName[value]}});
}

void Flow::Timeout(Time, Time value) { Event("rto_value", {{"seconds", value.GetSeconds()}}); }

void Flow::Tx(Ptr<const Packet> packet, const TcpHeader& header, Ptr<const TcpSocketBase>)
{
    txBytes += packet->GetSize();
    if (packetEvents) Event("tcp_tx", {{"bytes", packet->GetSize()},
        {"sequence", header.GetSequenceNumber().GetValue()}, {"flags", header.GetFlags()}});
}

void Flow::Rx(Ptr<const Packet>, const TcpHeader& header, Ptr<const TcpSocketBase>)
{
    if (!(header.GetFlags() & TcpHeader::ACK)) return;
    auto sequence = header.GetAckNumber();
    if (connected && sequence > SequenceNumber32(ackMark))
    {
        // 使用 TCP 序列号运算处理回绕，累计 ACK 只统计首次确认的字节。
        acked += sequence - SequenceNumber32(ackMark);
        ackMark = sequence.GetValue();
        Require(acked <= sent, "ACK exceeds submitted application data");
    }
    if (packetEvents) Event("tcp_ack", {{"ack", sequence.GetValue()}, {"acked_bytes", acked}});
}

void Flow::Retransmit(Ptr<const Packet> packet, const TcpHeader& header,
                     const Address&, const Address&, Ptr<const TcpSocketBase>)
{
    retransBytes += packet->GetSize();
    Event("retransmission", {{"bytes", packet->GetSize()},
        {"sequence", header.GetSequenceNumber().GetValue()},
        {"state", static_cast<int>(state->m_congState.Get())}});
}

void Flow::RttMeasured(Time value)
{
    Require(value.IsStrictlyPositive(), "RTT sample must be positive");
    double ms = value.GetSeconds() * 1000;
    rttSamples.push_back(ms);
    minRtt = std::min(minRtt, ms);
    Event("rtt", {{"ms", ms}});
}

void Flow::Computed(uint32_t cwnd, uint32_t flight, uint32_t result)
{
    lastThresholdTime = SecondsNow();
    Event("threshold_compute", {{"cwnd_bytes", cwnd}, {"flight_bytes", flight},
        {"ssthresh_bytes", result}, {"decision_id", decisionId}, {"beta", beta},
        {"algorithm", config.at("algorithm")}});
}

void Flow::Start()
{
    actualStart = SecondsNow();
    producing = true;
    socket = DynamicCast<TcpSocketBase>(Socket::CreateSocket(sender, TcpSocketFactory::GetTypeId()));
    Require(socket != nullptr, "TCP socket creation failed");
    auto estimator = CreateObject<RttObserver>();
    estimator->observer = [this](Time value) { RttMeasured(value); };
    socket->SetRtt(estimator);
    std::string algorithm = config.at("algorithm");
    if (algorithm == "cubic")
    {
        auto controller = CreateObject<ObservedCubic>();
        DoubleValue configuredBeta;
        controller->GetAttribute("Beta", configuredBeta);
        beta = configuredBeta.Get();
        controller->thresholdObserver = [this](auto w, auto f, auto t) { Computed(w, f, t); };
        socket->SetCongestionControlAlgorithm(controller);
        state = controller->state;
    }
    else
    {
        Ptr<ObservedReno> controller;
        if (algorithm == "glm" || algorithm == "fixed")
        {
            adaptive = CreateObject<TcpGlmReno>();
            beta = algorithm == "fixed" ? config.at("beta").get<double>() : 0.5;
            adaptive->beta = beta;
            adaptive->initialBeta = beta;
            controller = adaptive;
        }
        else controller = CreateObject<ObservedReno>();
        controller->thresholdObserver = [this](auto w, auto f, auto t) { Computed(w, f, t); };
        socket->SetCongestionControlAlgorithm(controller);
        state = controller->state;
    }

    // 在 Connect 和首次发送之前注册全部协议事件。
    Require(socket->TraceConnectWithoutContext("CongestionWindow", MakeCallback(&Flow::Cwnd, this)), "cwnd trace");
    Require(socket->TraceConnectWithoutContext("SlowStartThreshold", MakeCallback(&Flow::Threshold, this)), "threshold trace");
    Require(socket->TraceConnectWithoutContext("CongState", MakeCallback(&Flow::Congestion, this)), "state trace");
    Require(socket->TraceConnectWithoutContext("RTO", MakeCallback(&Flow::Timeout, this)), "RTO trace");
    Require(socket->TraceConnectWithoutContext("Tx", MakeCallback(&Flow::Tx, this)), "Tx trace");
    Require(socket->TraceConnectWithoutContext("Rx", MakeCallback(&Flow::Rx, this)), "Rx trace");
    Require(socket->TraceConnectWithoutContext("Retransmission", MakeCallback(&Flow::Retransmit, this)), "retransmission trace");
    socket->SetConnectCallback(MakeCallback(&Flow::Connected, this), MakeCallback(&Flow::Failed, this));
    socket->SetSendCallback(MakeCallback(&Flow::Available, this));
    Require(socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 40000 + id)) == 0, "TCP bind failed");
    Require(socket->Connect(InetSocketAddress(destination, 8000 + id)) == 0, "TCP connect failed");
    Event("source_started", {{"algorithm", algorithm}, {"beta", beta}});
}

bool Flow::Active() const { return socket && (producing || acked < sent); }

Json Flow::Observe()
{
    uint64_t tx = txBytes - previousTx;
    uint64_t retrans = retransBytes - previousRetrans;
    uint64_t delivered = acked - previousAcked;
    Json mean = nullptr, p95 = nullptr;
    if (!rttSamples.empty())
    {
        mean = std::accumulate(rttSamples.begin(), rttSamples.end(), 0.0) / rttSamples.size();
        std::sort(rttSamples.begin(), rttSamples.end());
        p95 = rttSamples.at(static_cast<size_t>(std::ceil(0.95 * rttSamples.size())) - 1);
    }
    Json row = {{"window", ++window}, {"end_s", SecondsNow()}, {"duration_s", 1.0},
        {"rtt_mean_ms", mean}, {"rtt_p95_ms", p95}, {"rtt_samples", rttSamples.size()},
        {"min_rtt_ms", std::isfinite(minRtt) ? Json(minRtt) : Json(nullptr)},
        {"srtt_ms", state->m_srtt.Get().GetSeconds() * 1000},
        {"rtt_inflation", mean.is_null() ? Json(nullptr) : Json(mean.get<double>() / minRtt - 1)},
        {"retransmission_ratio", tx ? Json(static_cast<double>(retrans) / tx) : Json(nullptr)},
        {"ack_rate_bps", delivered * 8.0}, {"tx_bytes", tx}, {"retrans_bytes", retrans},
        {"cwnd_bytes", static_cast<uint32_t>(state->m_cWnd)},
        {"ssthresh_bytes", static_cast<uint32_t>(state->m_ssThresh)},
        {"congestion_state", TcpSocketState::TcpCongStateName[state->m_congState.Get()]}};
    history.push_back(row);
    if (history.size() > 5) history.pop_front();
    previousTx = txBytes;
    previousRetrans = retransBytes;
    previousAcked = acked;
    rttSamples.clear();
    return {{"flow", id}, {"time_s", SecondsNow()}, {"history", history},
        {"previous_action", {{"beta", beta}, {"decision_id", decisionId},
            {"activated_at_s", activatedAt}, {"threshold_at_s", lastThresholdTime}}}};
}

void Flow::Activate(Json action)
{
    beta = action.at("beta").get<double>();
    Require(beta == 0.4 || beta == 0.5 || beta == 0.6 || beta == 0.7 || beta == 0.8, "invalid beta");
    decisionId = action.at("decision_id").get<std::string>();
    adaptive->beta = beta;
    activatedAt = SecondsNow();
    Event("action", {{"beta", beta}, {"decision_id", decisionId}});
}
}
