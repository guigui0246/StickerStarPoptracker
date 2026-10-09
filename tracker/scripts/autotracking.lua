-- AP mappings are supplied by the shared catalog in slot data. A checked
-- location updates only its marker; it never grants the location's item.
local item_map = {}
local location_map = {}
local received_indices = {}
local received_counts = {}

local function object_for(code)
    return Tracker:FindObjectForCode(code)
end

local function apply_count(mapping, count)
    local object = object_for(mapping.code)
    if not object then return end
    if mapping.type == "toggle" then
        object.Active = count > 0
    elseif mapping.type == "consumable" then
        object.AcquiredCount = math.min(count, object.MaxCount)
    elseif mapping.type == "progressive" then
        object.CurrentStage = math.min(count, mapping.max_stage)
    end
end

local function bulk(callback)
    Tracker.BulkUpdate = true
    local success, message = pcall(callback)
    Tracker.BulkUpdate = false
    if not success then print("Sticker Star tracking: " .. tostring(message)) end
end

local function reset()
    bulk(function()
        for _, mapping in pairs(item_map) do apply_count(mapping, 0) end
        for _, code in pairs(location_map) do
            local object = object_for(code)
            if object then object.AvailableChestCount = object.ChestCount end
        end
    end)
    item_map, location_map = {}, {}
    received_indices, received_counts = {}, {}
end

local function clear(slot_data)
    reset()
    if type(slot_data) ~= "table" or slot_data.logic_demo then return end
    local mappings = slot_data.tracker
    if type(mappings) ~= "table" or mappings.format_version ~= 1
        or type(mappings.catalog_hash) ~= "string" or #mappings.catalog_hash ~= 64
        or not mappings.catalog_hash:match("^[0-9a-f]+$")
        or mappings.catalog_hash ~= slot_data.catalog_hash then
        print("Sticker Star tracking requires matching catalog mappings.")
        return
    end
    if TRACKER_CATALOG_HASH and TRACKER_CATALOG_HASH ~= mappings.catalog_hash then
        print("Sticker Star tracker and seed use different catalogs.")
        return
    end
    if type(mappings.items) ~= "table" or type(mappings.locations) ~= "table" then return end
    for id, mapping in pairs(mappings.items) do
        if not tonumber(id) or type(mapping) ~= "table" or type(mapping.code) ~= "string"
            or not object_for(mapping.code)
            or (mapping.type ~= "toggle" and mapping.type ~= "consumable" and mapping.type ~= "progressive")
            or (mapping.type == "progressive" and (type(mapping.max_stage) ~= "number" or mapping.max_stage < 0 or mapping.max_stage ~= math.floor(mapping.max_stage))) then
            print("Sticker Star tracking has an unsupported item mapping.")
            return
        end
        local numeric_id = tonumber(id)
        if numeric_id < 0 or numeric_id ~= math.floor(numeric_id) then return end
        local object = object_for(mapping.code)
        if object.Type and object.Type ~= mapping.type then return end
    end
    local markers = {}
    for id, code in pairs(mappings.locations) do
        if not tonumber(id) or type(code) ~= "string" or code:sub(1, 1) ~= "@" or not object_for(code) then
            print("Sticker Star tracking has an unsupported location mapping.")
            return
        end
        local numeric_id = tonumber(id)
        if numeric_id < 0 or numeric_id ~= math.floor(numeric_id) then return end
        if markers[code] then return end
        markers[code] = true
    end
    for id, mapping in pairs(mappings.items) do item_map[tonumber(id)] = mapping end
    for id, code in pairs(mappings.locations) do location_map[tonumber(id)] = code end
    bulk(function()
        for _, mapping in pairs(item_map) do apply_count(mapping, 0) end
        for _, code in pairs(location_map) do
            local object = object_for(code)
            object.AvailableChestCount = object.ChestCount
        end
    end)
    -- Reconnecting replays authoritative items and checks into a clean state.
    for _, id in ipairs(Archipelago.CheckedLocations or {}) do
        local code = location_map[id]
        if code then object_for(code).AvailableChestCount = 0 end
    end
end

local function item(index, id)
    if received_indices[index] then return end
    received_indices[index] = true
    local mapping = item_map[id]
    if not mapping then return end
    local count = (received_counts[mapping.code] or 0) + 1
    received_counts[mapping.code] = count
    apply_count(mapping, count)
end

local function location(id)
    local code = location_map[id]
    if not code then return end
    local object = object_for(code)
    if object then object.AvailableChestCount = 0 end
end

if Archipelago then
    Archipelago:AddClearHandler("Sticker Star seed", clear)
    Archipelago:AddItemHandler("Sticker Star received items", item)
    Archipelago:AddLocationHandler("Sticker Star checked locations", location)
end
