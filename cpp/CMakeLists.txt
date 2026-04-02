cmake_minimum_required(VERSION 3.16)
project(hcp_worker VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(MSVC)
  add_compile_options(/W4 /permissive-)
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

add_executable(hcp_worker
  src/net.cpp
  src/worker_main.cpp
)

target_include_directories(hcp_worker PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/include)

if(WIN32)
  target_link_libraries(hcp_worker PRIVATE ws2_32)
endif()

install(TARGETS hcp_worker RUNTIME DESTINATION bin)
