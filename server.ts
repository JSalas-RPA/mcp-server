import { FastMCP } from "npm:fastmcp@3.9.0";
import { z } from "npm:zod@4.0.5";
import { roll } from "npm:@half-elf/rogue@1.0.1";

const server = new FastMCP({
  name: "DMCP - MCP for Dungeons and Dragons",
  version: "0.1.0",
});

const description = `
Given a string describing a dice roll in Dungeons and Dragons, 
provide a result of the roll.

Example input: 2d6 + 1d4
Example output: 14
`;

server.addTool({
  name: "roll",
  description,
  parameters: z.object({ diceRollExpression: z.string() }),
  execute: async (args) => {
    try {
      return String(roll(args.diceRollExpression));
    } catch (err) {
      return `Error parsing dice expression: ${err.message}`;
    }
  },
});

// Puerto fijo 7000
const PORT = 7000;

server.start({
  transportType: "httpStream",
  httpStream: { port: PORT },
});

console.log(`Servidor MCP iniciado en http://0.0.0.0:${PORT}`);
