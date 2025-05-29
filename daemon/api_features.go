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

package daemon

import (
	"net/http"

	"github.com/snapcore/snapd/overlord/auth"
)

var snapFeaturesCmd = &Command{
	Path:       "/v2/features",
	GET:        getFeatures,
	ReadAccess: openAccess{},
}

type featureResponse struct {
	Tasks      []string          `json:"tasks"`
	Interfaces []string          `json:"interfaces"`
	Endpoints  []featureEndpoint `json:"endpoints"`
}

func getFeatures(c *Command, r *http.Request, user *auth.UserState) Response {
	runner := c.d.overlord.TaskRunner()
	tasks := runner.KnownTaskKinds()

	ifaces := c.d.overlord.InterfaceManager().Repository().AllInterfaces()
	inames := make([]string, len(ifaces))
	for i, iface := range ifaces {
		inames[i] = iface.Name()
	}

	resp := featureResponse{Tasks: tasks, Interfaces: inames, Endpoints: featureList}
	return SyncResponse(resp)
}
