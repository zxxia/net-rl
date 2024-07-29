CXX = g++

.PHONY: all clean

OBJ_DIR := build/obj
BIN_DIR := build/bin

# SOURCES := $(wildcard *.cc)
SOURCES := $(shell find * -type f ! -name '*_test.cc' -name '*.cc')
OBJECTS := $(addprefix $(OBJ_DIR)/, $(patsubst %.cc, %.o, $(SOURCES)))
_builddirs := $(shell mkdir -p $(BIN_DIR); for OBJ in $(OBJECTS); do mkdir -p $$(dirname $$OBJ); done)
DEPENDS := $(addprefix $(OBJ_DIR)/, $(patsubst %.cc, %.d, $(SOURCES)))

DEPFLAGS := -MMD -MP
WARNING := -Wall -Wextra -Wpedantic #-Werror
CXXFLAGS := -g -std=c++17

RET := $(shell python3-config --cflags --embed > /dev/null 2>&1; echo $$?)
ifeq ($(RET),1)
   PYTHONCFLAGS := $(shell python3-config --cflags)
   PYTHONLDFLAGS := $(shell python3-config --ldflags)
else
   PYTHONCFLAGS := $(shell python3-config --cflags --embed)
   PYTHONLDFLAGS := $(shell python3-config --ldflags --embed)
endif
PYTHONCFLAGS := $(filter-out -O3 -O2 -DNDEBUG,$(PYTHONCFLAGS))
CXXFLAGS := $(CXXFLAGS) $(WARNING) $(DEPFLAGS) $(PYTHONCFLAGS)
uniq = $(if $1,$(firstword $1) $(call uniq,$(filter-out $(firstword $1),$1)))
CXXFLAGS := $(call uniq,$(CXXFLAGS))
PYTHONLDFLAGS := $(call uniq,$(PYTHONLDFLAGS))
# $(info $(PYTHONLDFLAGS))
# $(info $(PYTHONLDFLAGS))

all: $(BIN_DIR)/sim

$(OBJ_DIR)/%.o: %.cc Makefile
	$(CXX) $(CXXFLAGS) -I. -c $< -o $@

$(BIN_DIR)/sim: $(OBJECTS)
	$(CXX) $^ $(PYTHONLDFLAGS) -o $@
clean:
	rm -rf $(BIN_DIR) $(OBJ_DIR)

-include $(DEPENDS)
