#include "network-monitor.h"
#include <ns3/internet-module.h>
#include <ns3/ppp-header.h>

namespace lab
{
using namespace ns3;

static int TcpFlow(Ptr<const Packet> packet)
{
    TcpHeader tcp;
    packet->PeekHeader(tcp);
    if (tcp.GetDestinationPort() >= 8000 && tcp.GetDestinationPort() < 8032)
        return tcp.GetDestinationPort() - 8000;
    if (tcp.GetSourcePort() >= 8000 && tcp.GetSourcePort() < 8032)
        return tcp.GetSourcePort() - 8000;
    return -1;
}

int DeviceFlow(Ptr<const Packet> packet)
{
    auto copy = packet->Copy();
    PppHeader ppp;
    Ipv4Header ipv4;
    copy->RemoveHeader(ppp);
    if (ppp.GetProtocol() != 0x0021) return -1;
    copy->RemoveHeader(ipv4);
    if (ipv4.GetProtocol() != 6) return -1;
    return TcpFlow(copy);
}

static int DiscFlow(Ptr<const QueueDiscItem> item)
{
    auto ipv4 = DynamicCast<const Ipv4QueueDiscItem>(item);
    if (!ipv4 || ipv4->GetHeader().GetProtocol() != 6) return -1;
    return TcpFlow(item->GetPacket());
}

TypeId ObservedError::GetTypeId()
{
    static TypeId tid = TypeId("ns3::LabObservedError")
        .SetParent<ErrorModel>().AddConstructor<ObservedError>();
    return tid;
}

bool ObservedError::DoCorrupt(Ptr<Packet> packet)
{
    ++checks;
    bool lost = model->IsCorrupt(packet);
    if (lost)
    {
        ++drops;
        journal->Write("error_drop", {{"flow", DeviceFlow(packet)},
            {"bytes", packet->GetSize()}, {"check_index", checks - 1}});
    }
    return lost;
}

void ObservedError::DoReset() { checks = 0; drops = 0; model->Reset(); }

QueueMonitor::QueueMonitor(Journal& log, std::string label)
    : journal(log), name(std::move(label)) {}

void QueueMonitor::Enter(uint64_t uid) { ++arrivals; entered[uid].push_back(SecondsNow()); }

double QueueMonitor::Leave(uint64_t uid)
{
    auto found = entered.find(uid);
    Require(found != entered.end() && !found->second.empty(), "queue departure without arrival");
    double delay = SecondsNow() - found->second.front();
    found->second.pop_front();
    if (found->second.empty()) entered.erase(found);
    return delay;
}

void QueueMonitor::DiscEnqueue(Ptr<const QueueDiscItem> item) { Enter(item->GetPacket()->GetUid()); }

void QueueMonitor::DiscDequeue(Ptr<const QueueDiscItem> item)
{
    journal.Write("queue_delay", {{"queue", name}, {"flow", DiscFlow(item)},
        {"delay_s", Leave(item->GetPacket()->GetUid())}});
}

void QueueMonitor::DiscDrop(Ptr<const QueueDiscItem> item, const char* reason)
{
    ++drops;
    journal.Write("queue_drop", {{"queue", name}, {"flow", DiscFlow(item)},
        {"reason", reason}, {"bytes", item->GetSize()}});
}

void QueueMonitor::DeviceEnqueue(Ptr<const Packet> packet) { Enter(packet->GetUid()); }

void QueueMonitor::DeviceDequeue(Ptr<const Packet> packet)
{
    journal.Write("queue_delay", {{"queue", name}, {"flow", DeviceFlow(packet)},
        {"delay_s", Leave(packet->GetUid())}});
}

void QueueMonitor::DeviceDrop(Ptr<const Packet> packet)
{
    ++drops;
    journal.Write("queue_drop", {{"queue", name}, {"flow", DeviceFlow(packet)},
        {"reason", "device_limit"}, {"bytes", packet->GetSize()}});
}
}
