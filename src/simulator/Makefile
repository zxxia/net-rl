CC = g++

.PHONY: all clean

OBJ_DIR := build/obj
BIN_DIR := build/bin

# SOURCES := $(wildcard *.cc)
SOURCES := $(shell find * -type f ! -name '*_test.cc' -name '*.cc')
OBJECTS := $(addprefix $(OBJ_DIR)/, $(patsubst %.cc, %.o, $(SOURCES)))
_builddirs := $(shell mkdir -p $(BIN_DIR); for OBJ in $(OBJECTS); do mkdir -p $$(dirname $$OBJ); done)
DEPENDS := $(addprefix $(OBJ_DIR)/, $(patsubst %.cc, %.d, $(SOURCES)))

DEPFLAGS := -MMD -MP
WARNING := -Wall -Wextra #-Werror
CXXFLAGS := -g -std=c++17

all: $(BIN_DIR)/sim

$(OBJ_DIR)/%.o: %.cc Makefile
	$(CC) $(CXXFLAGS) $(WARNING) -I. $(DEPFLAGS) -c $< -o $@

$(BIN_DIR)/sim: $(OBJECTS)
	$(CC) $(CXXFLAGS) $(DEPFLAGS) $^ -o $@
clean:
	rm -rf $(BIN_DIR) $(OBJ_DIR)

-include $(DEPENDS)
