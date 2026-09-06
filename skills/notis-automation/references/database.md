### Trigger type: database (Notis record change)

Fires when records in a native Notis database are added or changed. Use `LOCAL_NOTIS_DATABASE_LIST_DATABASES` and `LOCAL_NOTIS_DATABASE_GET_DATABASE` (see the `notis-query` skill) to resolve the real `database_id` and the exact `property_id`s before building the config — never guess them.

The config is `{ database_id, root }`, where `root` is a condition tree. Each condition's `event` is one of `page_added` (record inserted), `any_property_edited` (any property changed), or `property_edited` (a specific property changed, requires `property_id` + `comparator`). Comparators depend on the property kind (e.g. `equals`, `changed_from_to`, `contains`, `greater_than`, `before`). `changed_from_to` needs `from_value` + `to_value`; value-based comparators need `value`.

```json
{
  "trigger_type": "database",
  "name": "Notify on task done",
  "prompt": "A task was just marked Done. Run /task-followup to add a note and check for follow-ups.",
  "database_trigger_config": {
    "database_id": "tasks-db-id",
    "root": {
      "kind": "group",
      "operator": "and",
      "children": [
        {
          "kind": "condition",
          "event": "property_edited",
          "property_id": "prop_status",
          "comparator": "changed_from_to",
          "from_value": "In Progress",
          "to_value": "Done"
        }
      ]
    }
  }
}
```
