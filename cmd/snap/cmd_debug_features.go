// -*- Mode: Go; indent-tabs-mode: t -*-

/*
 * Copyright (C) 2025 Canonical Ltd
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 *
 */

package main

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jessevdk/go-flags"
)

type cmdDebugFeatures struct {
	clientMixin
}

func init() {
	addDebugCommand("features",
		"Obtain the complete list of feature tags",
		`Display json output that contains the complete list 
		of feature tags present in snapd and snap`,
		func() flags.Commander { return &cmdDebugFeatures{} },
		nil,
		nil,
	)
}

func (x *cmdDebugFeatures) Execute(args []string) error {
	x.setClient(mkClient())
	rsp, err := x.client.DebugRaw(context.Background(), "GET", "/v2/features", nil, nil, nil)
	if err != nil {
		return err
	}
	defer rsp.Body.Close()
	var temp map[string]any
	if err := json.NewDecoder(rsp.Body).Decode(&temp); err != nil {
		return err
	}
	result := temp["result"].(map[string]any)
	result["commands"] = map[string][]string{}
	commandsResults := result["commands"].(map[string][]string)
	for _, cmd := range commands {
		commandsResults[cmd.name] = []string{}
		for _, args := range cmd.argDescs {
			commandsResults[cmd.name] = append(commandsResults[cmd.name], args.name)
		}
	}
	for _, cmd := range debugCommands {
		commandsResults[cmd.name] = []string{}
		for _, args := range cmd.argDescs {
			commandsResults[cmd.name] = append(commandsResults[cmd.name], args.name)
		}
	}
	for _, cmd := range routineCommands {
		commandsResults[cmd.name] = []string{}
		for _, args := range cmd.argDescs {
			commandsResults[cmd.name] = append(commandsResults[cmd.name], args.name)
		}
	}
	enc := json.NewEncoder(Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(temp); err != nil {
		return err
	}

	if rsp.StatusCode >= 400 {
		// caller wants to fail on non success requests
		return fmt.Errorf("request failed with status %v", rsp.Status)
	}
	return nil
}
