#include "application/application.h"
#include "packet/packet.h"

#ifndef FILE_TRANSFER_H
#define FILE_TRANSFER_H

class FileSender : public ApplicationInterface {
public:
  unsigned int GetPktToSendSize() const override { return Packet::MSS; }

  std::unique_ptr<ApplicationData> GetPktToSend() override {
    auto app_data = std::make_unique<ApplicationData>();
    app_data->size_byte = GetPktToSendSize();
    return app_data;
  }

  void DeliverPkt(std::unique_ptr<Packet>) override {}

  void Tick() override {}

  void Reset() override {}
};

class FileReceiver : public ApplicationInterface {
public:
  unsigned int GetPktToSendSize() const override { return 0; }

  std::unique_ptr<ApplicationData> GetPktToSend() override { return nullptr; }

  void DeliverPkt(std::unique_ptr<Packet>) override {}

  void Tick() override {}

  void Reset() override {}
};

#endif // FILE_TRANSFER_H
