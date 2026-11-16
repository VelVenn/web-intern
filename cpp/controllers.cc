#include "controllers.h"

#include <algorithm>
#include <cmath>

namespace lab
{
using namespace ns3;

TypeId ObservedReno::GetTypeId()
{
    static TypeId tid = TypeId("ns3::LabObservedReno")
        .SetParent<TcpLinuxReno>().AddConstructor<ObservedReno>();
    return tid;
}

void ObservedReno::Init(Ptr<TcpSocketState> tcb)
{
    state = tcb;
    TcpLinuxReno::Init(tcb);
}

uint32_t ObservedReno::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t flight)
{
    uint32_t result = TcpLinuxReno::GetSsThresh(tcb, flight);
    if (thresholdObserver) thresholdObserver(tcb->m_cWnd, flight, result);
    return result;
}

Ptr<TcpCongestionOps> ObservedReno::Fork() { return CreateObject<ObservedReno>(); }

TypeId ObservedCubic::GetTypeId()
{
    static TypeId tid = TypeId("ns3::LabObservedCubic")
        .SetParent<TcpCubic>().AddConstructor<ObservedCubic>();
    return tid;
}

void ObservedCubic::Init(Ptr<TcpSocketState> tcb)
{
    state = tcb;
    TcpCubic::Init(tcb);
}

uint32_t ObservedCubic::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t flight)
{
    uint32_t result = TcpCubic::GetSsThresh(tcb, flight);
    if (thresholdObserver) thresholdObserver(tcb->m_cWnd, flight, result);
    return result;
}

Ptr<TcpCongestionOps> ObservedCubic::Fork() { return CreateObject<ObservedCubic>(); }

TypeId TcpGlmReno::GetTypeId()
{
    static TypeId tid = TypeId("ns3::TcpGlmReno")
        .SetParent<ObservedReno>().AddConstructor<TcpGlmReno>();
    return tid;
}

std::string TcpGlmReno::GetName() const { return "TcpGlmReno"; }

uint32_t TcpGlmReno::GetSsThresh(Ptr<const TcpSocketState> tcb, uint32_t flight)
{
    auto segments = static_cast<uint32_t>(std::floor(beta * tcb->m_cWnd / tcb->m_segmentSize));
    uint32_t result = std::max(2U, segments) * tcb->m_segmentSize;
    if (thresholdObserver) thresholdObserver(tcb->m_cWnd, flight, result);
    return result;
}

Ptr<TcpCongestionOps> TcpGlmReno::Fork()
{
    auto copy = CreateObject<TcpGlmReno>();
    copy->beta = initialBeta;
    copy->initialBeta = initialBeta;
    return copy;
}
}
