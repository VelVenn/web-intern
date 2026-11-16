cmake_minimum_required(VERSION 3.25)
project(tcp_glm_lab VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(ns3 3.49 EXACT CONFIG REQUIRED)

include(FetchContent)
set(JSON_BuildTests OFF CACHE BOOL "" FORCE)
set(JSON_Install OFF CACHE BOOL "" FORCE)
FetchContent_Declare(nlohmann_json
  URL https://github.com/nlohmann/json/releases/download/v3.12.0/json.tar.xz
  URL_HASH SHA256=42f6e95cad6ec532fd372391373363b62a14af6d771056dbfc86160e6dfff7aa
  DOWNLOAD_EXTRACT_TIMESTAMP TRUE)
FetchContent_MakeAvailable(nlohmann_json)

add_executable(tcp-sim cpp/main.cc cpp/controllers.cc cpp/flow.cc
  cpp/network-monitor.cc cpp/topology.cc cpp/experiment.cc)

target_link_libraries(tcp-sim PRIVATE nlohmann_json::nlohmann_json
  ns3::core ns3::network ns3::internet ns3::point-to-point
  ns3::applications ns3::traffic-control ns3::flow-monitor)

target_compile_options(tcp-sim PRIVATE -Wall -Wextra -Wpedantic)
target_compile_definitions(tcp-sim PRIVATE LAB_COMPILER="${CMAKE_CXX_COMPILER_ID}-${CMAKE_CXX_COMPILER_VERSION}")

include(CTest)
if(BUILD_TESTING)
  find_package(Python3 3.12 REQUIRED COMPONENTS Interpreter)
  add_test(NAME network-integration
    COMMAND ${Python3_EXECUTABLE} -m pytest -q -m "not api" ${PROJECT_SOURCE_DIR}/tests)
  set_tests_properties(network-integration PROPERTIES WORKING_DIRECTORY ${PROJECT_SOURCE_DIR}
    ENVIRONMENT "TCP_LAB_BINARY=$<TARGET_FILE:tcp-sim>")
endif()
