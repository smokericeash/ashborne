import { describe, expect, it } from "vitest";
import {
  operatorCommandCompletions,
  parseOperatorCommand,
} from "./operatorCommands";

describe("operator command parser", () => {
  it.each(["hostname", "whoami", "uname -a", "ps aux", "ip addr"])(
    "passes %s to the Kali controller as an SSH operation",
    (command) => {
      expect(parseOperatorCommand(`  ${command}  `)).toEqual({
        kind: "operation",
        command,
        executionMode: "ssh",
      });
    },
  );

  it("keeps workspace commands local and accepts general operations", () => {
    expect(parseOperatorCommand("deselect-all")).toEqual({
      kind: "local",
      command: "deselect-all",
    });
    expect(parseOperatorCommand("curl example.invalid")).toEqual({
      kind: "operation",
      command: "curl example.invalid",
      executionMode: "ssh",
    });
    expect(parseOperatorCommand("kali:nmap -sV $ASHBORNE_TARGET_IP")).toEqual({
      kind: "operation",
      command: "nmap -sV $ASHBORNE_TARGET_IP",
      executionMode: "local",
    });
  });

  it("offers bounded prefix completion", () => {
    expect(operatorCommandCompletions("hostn")).toEqual(["hostname"]);
    expect(operatorCommandCompletions("deselect-a")).toEqual(["deselect-all"]);
  });
});
