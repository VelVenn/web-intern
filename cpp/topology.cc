#include "experiment.h"

namespace lab
{
using namespace ns3;

void Experiment::LinkTx(unsigned direction, Ptr<const Packet> packet)
{
    journal.Write("link_tx", {{"direction", direction}, {"flow", DeviceFlow(packet)},
        {"bytes", packet->GetSize()},
        {"duration_s", rate.CalculateBytesTxTime(packet->GetSize()).GetSeconds()}});
}

void Experiment::Monitor(Ptr<NetDevice> device, Ptr<QueueDisc> disc, unsigned direction)
{
    auto q = std::make_unique<QueueMonitor>(journal, std::to_string(direction) + "_disc");
    Require(disc->TraceConnectWithoutContext("Enqueue", MakeCallback(&QueueMonitor::DiscEnqueue, q.get())), "disc enqueue trace");
    Require(disc->TraceConnectWithoutContext("Dequeue", MakeCallback(&QueueMonitor::DiscDequeue, q.get())), "disc dequeue trace");
    Require(disc->TraceConnectWithoutContext("DropBeforeEnqueue", MakeCallback(&QueueMonitor::DiscDrop, q.get())), "disc drop trace");
    queues.push_back(std::move(q));

    auto d = std::make_unique<QueueMonitor>(journal, std::to_string(direction) + "_device");
    auto queue = DynamicCast<PointToPointNetDevice>(device)->GetQueue();
    Require(queue->TraceConnectWithoutContext("Enqueue", MakeCallback(&QueueMonitor::DeviceEnqueue, d.get())), "device enqueue trace");
    Require(queue->TraceConnectWithoutContext("Dequeue", MakeCallback(&QueueMonitor::DeviceDequeue, d.get())), "device dequeue trace");
    Require(queue->TraceConnectWithoutContext("DropBeforeEnqueue", MakeCallback(&QueueMonitor::DeviceDrop, d.get())), "device drop trace");
    queues.push_back(std::move(d));
    Require(device->TraceConnectWithoutContext("PhyTxBegin",
        MakeCallback(&Experiment::LinkTx, this).Bind(direction)), "link trace");
}

void Experiment::Build()
{
    RngSeedManager::SetSeed(config.at("seed"));
    RngSeedManager::SetRun(config.at("run"));
    Config::SetDefault("ns3::TcpSocket::SegmentSize", UintegerValue(1448));
    Config::SetDefault("ns3::TcpSocket::InitialCwnd", UintegerValue(config.at("initial_cwnd")));
    Config::SetDefault("ns3::TcpSocket::InitialSlowStartThreshold", UintegerValue(config.at("initial_ssthresh")));
    Config::SetDefault("ns3::TcpSocket::SndBufSize", UintegerValue(16 * 1024 * 1024));
    Config::SetDefault("ns3::TcpSocket::RcvBufSize", UintegerValue(16 * 1024 * 1024));
    Config::SetDefault("ns3::TcpSocket::DelAckCount", UintegerValue(config.at("delayed_ack")));
    Config::SetDefault("ns3::TcpSocketBase::Sack", BooleanValue(config.at("sack")));
    Config::SetDefault("ns3::TcpSocketBase::Timestamp", BooleanValue(true));
    Config::SetDefault("ns3::TcpSocketBase::WindowScaling", BooleanValue(true));
    Config::SetDefault("ns3::TcpSocketBase::MinRto", TimeValue(Seconds(1)));
    Config::SetDefault("ns3::TcpSocketBase::UseEcn", EnumValue(TcpSocketState::Off));
    Config::SetDefault("ns3::TcpL4Protocol::RecoveryType", TypeIdValue(
        config.at("recovery") == "classic" ? TcpClassicRecovery::GetTypeId() : TcpPrrRecovery::GetTypeId()));

    NodeContainer routers;
    routers.Create(2);
    InternetStackHelper internet;
    internet.Install(routers);
    PointToPointHelper central;
    central.SetDeviceAttribute("DataRate", DataRateValue(rate));
    central.SetChannelAttribute("Delay", TimeValue(MilliSeconds(config.at("delay_ms").get<double>())));
    central.SetQueue("ns3::DropTailQueue<Packet>", "MaxSize", QueueSizeValue(QueueSize("1p")));
    bottleneck = central.Install(routers);

    // 在分配地址前安装指定队列，确保实验采用同一排队机制。
    TrafficControlHelper traffic;
    traffic.SetRootQueueDisc("ns3::FifoQueueDisc", "MaxSize",
        QueueSizeValue(QueueSize(std::to_string(config.at("queue_bytes").get<uint32_t>()) + "B")));
    auto discs = traffic.Install(bottleneck);
    Ipv4AddressHelper address;
    address.SetBase("10.0.0.0", "255.255.255.0");
    address.Assign(bottleneck);
    for (unsigned i = 0; i < 2; ++i) Monitor(bottleneck.Get(i), discs.Get(i), i);

    auto randomError = CreateObject<RateErrorModel>();
    randomError->SetUnit(RateErrorModel::ERROR_UNIT_PACKET);
    randomError->SetRate(config.at("error_rate"));
    randomError->AssignStreams(1000);
    error = CreateObject<ObservedError>();
    error->journal = &journal;
    if (config.at("drop_indices").empty()) error->model = randomError;
    else
    {
        auto deterministic = CreateObject<ReceiveListErrorModel>();
        deterministic->SetList(config.at("drop_indices").get<std::list<uint32_t>>());
        error->model = deterministic;
    }
    DynamicCast<PointToPointNetDevice>(bottleneck.Get(1))->SetReceiveErrorModel(error);
    if (!config.at("outage_start_s").is_null())
    {
        Simulator::Schedule(Seconds(config.at("outage_start_s").get<double>()), [this, randomError] {
            randomError->SetRate(1);
            journal.Write("outage_start");
        });
        Simulator::Schedule(Seconds(config.at("outage_end_s").get<double>()), [this, randomError] {
            randomError->SetRate(config.at("error_rate"));
            journal.Write("outage_end");
        });
    }

    int i = 0;
    for (const auto& settings : config.at("flows"))
    {
        auto f = std::make_unique<Flow>(i, settings, journal, config.at("packet_events"));
        NodeContainer nodes;
        nodes.Create(2);
        internet.Install(nodes);
        PointToPointHelper access;
        access.SetDeviceAttribute("DataRate", StringValue("1Gbps"));
        access.SetChannelAttribute("Delay", TimeValue(MilliSeconds(settings.at("access_delay_ms").get<double>())));
        access.SetQueue("ns3::DropTailQueue<Packet>", "MaxSize", QueueSizeValue(QueueSize("1p")));
        auto left = access.Install(nodes.Get(0), routers.Get(0));
        auto right = access.Install(routers.Get(1), nodes.Get(1));
        TrafficControlHelper accessTraffic;
        accessTraffic.SetRootQueueDisc("ns3::FifoQueueDisc", "MaxSize", QueueSizeValue(QueueSize("16777216B")));
        accessTraffic.Install(left);
        accessTraffic.Install(right);
        address.NewNetwork();
        auto leftAddresses = address.Assign(left);
        address.NewNetwork();
        auto rightAddresses = address.Assign(right);
        bool reverse = settings.at("reverse");
        f->sender = nodes.Get(reverse ? 1 : 0);
        f->receiver = nodes.Get(reverse ? 0 : 1);
        f->destination = reverse ? leftAddresses.GetAddress(0) : rightAddresses.GetAddress(1);
        PacketSinkHelper sinkHelper("ns3::TcpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), 8000 + i));
        auto sinks = sinkHelper.Install(f->receiver);
        sinks.Start(Seconds(0));
        f->sink = DynamicCast<PacketSink>(sinks.Get(0));
        Require(f->sink->TraceConnectWithoutContext("RxWithAddresses", MakeCallback(&Flow::Receive, f.get())), "sink trace");
        auto jitter = CreateObject<UniformRandomVariable>();
        jitter->SetStream(2000 + i);
        double start = settings.at("start_s").get<double>() + jitter->GetValue(0, config.at("start_jitter_s"));
        Flow* ptr = f.get();
        Simulator::Schedule(Seconds(start), &Flow::Start, ptr);
        Simulator::Schedule(Seconds(settings.at("stop_s").get<double>()), &Flow::Stop, ptr);
        Simulator::Schedule(Seconds(start + 1), &Experiment::Decision, this, ptr);
        flows.push_back(std::move(f));
        ++i;
    }
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    for (const auto& change : config.at("changes"))
    {
        Simulator::Schedule(Seconds(change.at("time_s").get<double>()), [this, change] {
            if (!change.at("rate_mbps").is_null())
            {
                rate = DataRate(static_cast<uint64_t>(change.at("rate_mbps").get<double>() * 1e6));
                for (unsigned j = 0; j < 2; ++j)
                    DynamicCast<PointToPointNetDevice>(bottleneck.Get(j))->SetDataRate(rate);
            }
            if (!change.at("delay_ms").is_null())
                bottleneck.Get(0)->GetChannel()->SetAttribute("Delay",
                    TimeValue(MilliSeconds(change.at("delay_ms").get<double>())));
            journal.Write("network_change", change);
        });
    }
    if (config.at("pcap")) central.EnablePcapAll((directory / "capture").string());
    Simulator::ScheduleNow(&Experiment::Sample, this);
}
}
