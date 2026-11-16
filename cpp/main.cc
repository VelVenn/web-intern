#include "support.h"

int main(int argc, char** argv)
{
    lab::Require(argc == 3, "Usage: tcp-sim CONFIG.json OUTPUT_DIRECTORY");
    std::ifstream input(argv[1]);
    lab::Require(input.good(), "configuration file cannot be opened");
    auto config = lab::Json::parse(input);
    auto directory = lab::fs::absolute(argv[2]);
    lab::Require(lab::fs::is_directory(directory), "output directory must exist");
    lab::Require(!lab::fs::exists(directory / "events.jsonl"), "refusing to overwrite simulation events");
    lab::RunExperiment(std::move(config), directory);
}
