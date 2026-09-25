package main

import (
  "bytes"
  "encoding/json"
  "fmt"
  "net/http"
)

type Request struct { JSONRPC string `json:"jsonrpc"`; ID int `json:"id"`; Method string `json:"method"`; Params map[string]any `json:"params"` }

func Call(url, method, name string, params map[string]any) ([]byte, error) {
  body, err := json.Marshal(Request{"2.0", 1, method, params})
  if err != nil { return nil, err }
  req, err := http.NewRequest(http.MethodPost, url, bytes.NewReader(body))
  if err != nil { return nil, err }
  req.Header.Set("Content-Type", "application/json")
  req.Header.Set("MCP-Protocol-Version", "2026-07-28")
  req.Header.Set("Mcp-Method", method)
  if name != "" { req.Header.Set("Mcp-Name", name) }
  resp, err := http.DefaultClient.Do(req)
  if err != nil { return nil, err }
  defer resp.Body.Close()
  var out bytes.Buffer
  _, err = out.ReadFrom(resp.Body)
  if err != nil { return nil, err }
  if resp.StatusCode >= 300 { return nil, fmt.Errorf("MCP HTTP %d: %s", resp.StatusCode, out.String()) }
  return out.Bytes(), nil
}
