function has(item)
  return Tracker:ProviderCountForCode(item) > 0
end

function W1_BRIDGE()
  return has("paperization") and has("scrap_wooden_bridge")
end

function W1_SECRET()
  return has("paperization") and has("sticker_secret_door")
end

function W1_PIPE()
  return has("paperization") and has("scrap_green_warp_pipe")
end

function W1_GATE()
  return has("paperization") and has("scrap_white_gate")
end

function W1_FORTRESS()
  return has("paperization") and has("scrap_block_switch") and has("req_thing_scissors")
end

function W2_TABLET()
  return has("paperization") and has("scrap_tablet_piece_1") and has("scrap_tablet_piece_2") and has("scrap_tablet_piece_3")
end

function W2_BOSS()
  return W2_TABLET() and has("req_thing_bat")
end

function W3_BRIDGE()
  return has("paperization") and has("scrap_bridge_part_1") and has("scrap_bridge_part_2") and has("scrap_bridge_part_3")
end

function W4_BOO()
  return has("req_book_of_sealing") and (has("req_thing_fan") or has("req_thing_vacuum") or has("req_thing_faucet"))
end

function ALL_ROYALS()
  return has("royal_w1") and has("royal_w2") and has("royal_w3") and has("royal_w4") and has("royal_w5")
end

function W6_FINAL()
  return has("paperization") and has("req_thing_scissors") and has("req_thing_fan") and has("req_thing_battery")
end
