
import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Activity,
  Bell,
  ChartNoAxesCombined,
  ClipboardList,
  Clock,
  LogOut,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Users,
  Wallet,
  Wifi,
  WifiOff,
} from 'lucide-react'
import api from './api'
import './App.css'

type User = {
  id: number
  name: string
  email: string
  role: 'BUYER' | 'SUPPLIER' | 'ADMIN'
  company_name?: string
}

type Auction = {
  id: number
  start_time: string
  close_time: string
  forced_close_time: string
  status: string
  config: {
    trigger_type: string
    trigger_window_minutes: number
    extension_minutes: number
  }
}

type RFQ = {
  id: number
  reference_id: string
  name: string
  description?: string
  pickup_date: string
  service_date: string
  status: string
  auction: Auction
}

type Invitation = {
  participant_id: number
  rfq_id?: number
  rfq_reference_id: string
  rfq_name: string
  buyer_name: string
  status: string
  invited_at: string
  auction?: Auction
}

type Bid = {
  id: number
  auction_id: number
  supplier_id: number
  freight_charges: number
  origin_charges: number
  destination_charges: number
  total_price: number
  transit_time_days: number
  quote_valid_until: string
  submitted_at: string
}

type Ranking = {
  supplier_id: number
  rank: number
  total_price: number
  latest_bid_id: number
}

type EventItem = {
  id: number
  event_type: string
  reason?: string
  created_at: string
}

const money = (value: number | string) =>
  `₹${Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

const dateTime = (value?: string) =>
  value ? new Date(value).toLocaleString('en-IN') : '—'

const statusClass = (status: string) =>
  `status status-${status.toLowerCase()}`

const errorMessage = (err: any, fallback: string) =>
  err?.response?.data?.detail || err?.message || fallback

const triggerLabel = (trigger?: string) => {
  const labels: Record<string, string> = {
    ANY_BID: 'Any valid bid',
    ANY_RANK_CHANGE: 'Any ranking change',
    L1_RANK_CHANGE: 'L1 leader change',
  }

  return trigger ? labels[trigger] || trigger.replaceAll('_', ' ') : '—'
}

function Countdown({ closeTime }: { closeTime?: string }) {
  const [remaining, setRemaining] = useState('—')

  useEffect(() => {
    if (!closeTime) {
      setRemaining('Not available')
      return
    }

    const update = () => {
      const difference = new Date(closeTime).getTime() - Date.now()

      if (Number.isNaN(difference)) {
        setRemaining('Invalid date')
        return
      }

      if (difference <= 0) {
        setRemaining('Closing time reached')
        return
      }

      const totalSeconds = Math.floor(difference / 1000)
      const days = Math.floor(totalSeconds / 86400)
      const hours = Math.floor((totalSeconds % 86400) / 3600)
      const minutes = Math.floor((totalSeconds % 3600) / 60)
      const seconds = totalSeconds % 60

      setRemaining(
        `${days > 0 ? `${days}d ` : ''}${String(hours).padStart(2, '0')}:${String(
          minutes,
        ).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`,
      )
    }

    update()
    const interval = window.setInterval(update, 1000)

    return () => window.clearInterval(interval)
  }, [closeTime])

  return <strong className="countdown-value">{remaining}</strong>
}

function App() {
  const [user, setUser] = useState<User | null>(() => {
    try {
      const saved = localStorage.getItem('gocomet_user')
      return saved ? JSON.parse(saved) : null
    } catch {
      localStorage.removeItem('gocomet_user')
      localStorage.removeItem('gocomet_token')
      return null
    }
  })

  const [page, setPage] = useState('dashboard')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const [rfqs, setRfqs] = useState<RFQ[]>([])
  const [invitations, setInvitations] = useState<Invitation[]>([])
  const [lowestBids, setLowestBids] = useState<Record<number, number>>({})

  const [selectedAuction, setSelectedAuction] = useState<number | null>(null)
  const [bids, setBids] = useState<Bid[]>([])
  const [rankings, setRankings] = useState<Ranking[]>([])
  const [events, setEvents] = useState<EventItem[]>([])

  const [inviteEmails, setInviteEmails] = useState('')
  const [socketConnected, setSocketConnected] = useState(false)

  const [bidForm, setBidForm] = useState({
    freight_charges: '',
    origin_charges: '',
    destination_charges: '',
    transit_time_days: '5',
    quote_valid_until: '',
  })

  const flash = (message: string, isError = false) => {
    setError(isError ? message : '')
    setSuccess(isError ? '' : message)
  }

  const logout = () => {
    localStorage.removeItem('gocomet_token')
    localStorage.removeItem('gocomet_user')

    setUser(null)
    setPage('dashboard')
    setSelectedAuction(null)
    setSocketConnected(false)
    setRfqs([])
    setInvitations([])
    setLowestBids({})
  }

  const loadBuyerRFQs = useCallback(async () => {
    const response = await api.get('/rfqs/')
    const data: RFQ[] = response.data

    setRfqs(data)

    // Fetch rankings for each auction to show the current lowest bid.
    const results = await Promise.allSettled(
      data.map(async (rfq) => {
        const rankingResponse = await api.get(
          `/bids/auctions/${rfq.auction.id}/rankings`,
        )

        const auctionRankings: Ranking[] = rankingResponse.data

        return {
          auctionId: rfq.auction.id,
          lowestPrice:
            auctionRankings.length > 0
              ? Math.min(...auctionRankings.map((r) => Number(r.total_price)))
              : null,
        }
      }),
    )

    const updated: Record<number, number> = {}

    results.forEach((result) => {
      if (result.status === 'fulfilled' && result.value.lowestPrice !== null) {
        updated[result.value.auctionId] = result.value.lowestPrice
      }
    })

    setLowestBids(updated)
  }, [])

  const loadSupplierInvitations = useCallback(async () => {
    const response = await api.get('/participants/my-invitations')
    setInvitations(response.data)
  }, [])

  const loadDashboard = useCallback(async () => {
    if (!user) return

    setLoading(true)
    setError('')

    try {
      if (user.role === 'BUYER') {
        await loadBuyerRFQs()
      }

      if (user.role === 'SUPPLIER') {
        await loadSupplierInvitations()
      }
    } catch (err: any) {
      flash(errorMessage(err, 'Could not load dashboard data.'), true)
    } finally {
      setLoading(false)
    }
  }, [user, loadBuyerRFQs, loadSupplierInvitations])

  useEffect(() => {
    loadDashboard()
  }, [loadDashboard])

  const openAuction = async (auctionId: number) => {
    setSelectedAuction(auctionId)
    setPage('auction')
    setLoading(true)
    setError('')

    try {
      const [bidResponse, rankingResponse, eventResponse] = await Promise.all([
        api.get(`/bids/auctions/${auctionId}`),
        api.get(`/bids/auctions/${auctionId}/rankings`),
        api.get(`/bids/auctions/${auctionId}/events`),
      ])

      setBids(bidResponse.data)
      setRankings(rankingResponse.data)
      setEvents(eventResponse.data)
    } catch (err: any) {
      flash(errorMessage(err, 'Could not load auction details.'), true)
    } finally {
      setLoading(false)
    }
  }

  // WebSocket connection with automatic reconnect.
  useEffect(() => {
    if (!selectedAuction || !user) {
      setSocketConnected(false)
      return
    }

    const token = localStorage.getItem('gocomet_token')
    if (!token) return

    let socket: WebSocket | null = null
    let reconnectTimer: number | undefined
    let cancelled = false

    const connect = () => {
      if (cancelled) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socketUrl =
        `${protocol}//${window.location.hostname}:8000/ws/auctions/` +
        `${selectedAuction}?token=${encodeURIComponent(token)}`

      socket = new WebSocket(socketUrl)

      socket.onopen = () => {
        setSocketConnected(true)
      }

      socket.onmessage = () => {
        if (cancelled) return

        Promise.all([
          api.get(`/bids/auctions/${selectedAuction}`),
          api.get(`/bids/auctions/${selectedAuction}/rankings`),
          api.get(`/bids/auctions/${selectedAuction}/events`),
        ])
          .then(([bidResponse, rankingResponse, eventResponse]) => {
            if (cancelled) return
            setBids(bidResponse.data)
            setRankings(rankingResponse.data)
            setEvents(eventResponse.data)
          })
          .catch(() => {
            // The next WebSocket event or manual refresh can retry the request.
          })
      }

      socket.onclose = () => {
        setSocketConnected(false)

        if (!cancelled) {
          reconnectTimer = window.setTimeout(connect, 3000)
        }
      }

      socket.onerror = () => {
        setSocketConnected(false)
        socket?.close()
      }
    }

    connect()

    return () => {
      cancelled = true
      setSocketConnected(false)

      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }

      socket?.close()
    }
  }, [selectedAuction, user])

  const login = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setLoading(true)
    setError('')

    const form = new FormData(event.currentTarget)

    try {
      const response = await api.post('/auth/login', {
        email: form.get('email'),
        password: form.get('password'),
      })

      localStorage.setItem('gocomet_token', response.data.access_token)
      localStorage.setItem('gocomet_user', JSON.stringify(response.data.user))

      setUser(response.data.user)
      setPage('dashboard')
      flash(`Welcome, ${response.data.user.name}.`)
    } catch (err: any) {
      flash(errorMessage(err, 'Login failed. Check your credentials.'), true)
    } finally {
      setLoading(false)
    }
  }

  const createRFQ = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    setLoading(true)
    setError('')

    const form = new FormData(event.currentTarget)

    const localDateTime = (key: string) => {
      const value = String(form.get(key) || '')
      return value ? new Date(value).toISOString() : ''
    }

    const startTime = new Date(String(form.get('start_time'))).getTime()
    const closeTime = new Date(String(form.get('close_time'))).getTime()
    const forcedCloseTime = new Date(
      String(form.get('forced_close_time')),
    ).getTime()

    if (
      !Number.isFinite(startTime) ||
      !Number.isFinite(closeTime) ||
      !Number.isFinite(forcedCloseTime) ||
      startTime <= Date.now() ||
      closeTime <= startTime ||
      forcedCloseTime < closeTime
    ) {
      flash(
        'Check the auction schedule. Start must be in the future, and forced close must be at or after initial close.',
        true,
      )
      setLoading(false)
      return
    }

    try {
      await api.post('/rfqs/', {
        name: form.get('name'),
        description: form.get('description') || null,
        pickup_date: form.get('pickup_date'),
        service_date: form.get('service_date'),
        auction: {
          start_time: localDateTime('start_time'),
          close_time: localDateTime('close_time'),
          forced_close_time: localDateTime('forced_close_time'),
          config: {
            trigger_type: form.get('trigger_type'),
            trigger_window_minutes: Number(
              form.get('trigger_window_minutes'),
            ),
            extension_minutes: Number(form.get('extension_minutes')),
          },
        },
      })

      flash('RFQ and auction created successfully.')
      setPage('dashboard')
      await loadBuyerRFQs()
    } catch (err: any) {
      flash(
        errorMessage(err, 'Could not create RFQ. Check the entered dates.'),
        true,
      )
    } finally {
      setLoading(false)
    }
  }

  const publishRFQ = async (rfqId: number) => {
    setLoading(true)

    try {
      await api.post(`/rfqs/${rfqId}/publish`)
      flash('RFQ published successfully.')
      await loadBuyerRFQs()
    } catch (err: any) {
      flash(errorMessage(err, 'Could not publish RFQ.'), true)
    } finally {
      setLoading(false)
    }
  }

  const inviteSuppliers = async (rfqId: number) => {
    const emails = inviteEmails
      .split(/[,;\n]/)
      .map((email) => email.trim())
      .filter(Boolean)

    if (!emails.length) {
      flash('Enter at least one supplier email.', true)
      return
    }

    setLoading(true)

    try {
      await api.post(`/participants/rfqs/${rfqId}/invite`, {
        supplier_emails: emails,
      })

      setInviteEmails('')
      flash('Supplier invitation(s) sent.')
    } catch (err: any) {
      flash(errorMessage(err, 'Could not send invitations.'), true)
    } finally {
      setLoading(false)
    }
  }

  const invitationAction = async (
    id: number,
    action: 'accept' | 'decline',
  ) => {
    setLoading(true)

    try {
      await api.post(`/participants/${id}/${action}`)
      flash(`Invitation ${action}ed.`)
      await loadSupplierInvitations()
    } catch (err: any) {
      flash(errorMessage(err, `Could not ${action} invitation.`), true)
    } finally {
      setLoading(false)
    }
  }

  const submitBid = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!selectedAuction) return

    const quoteDate = new Date(bidForm.quote_valid_until)

    if (
      !bidForm.quote_valid_until ||
      Number.isNaN(quoteDate.getTime()) ||
      quoteDate.getTime() <= Date.now()
    ) {
      flash('Quote validity must be a future date and time.', true)
      return
    }

    setLoading(true)

    try {
      const response = await api.post(`/bids/auctions/${selectedAuction}`, {
        freight_charges: Number(bidForm.freight_charges),
        origin_charges: Number(bidForm.origin_charges),
        destination_charges: Number(bidForm.destination_charges),
        transit_time_days: Number(bidForm.transit_time_days),
        quote_valid_until: quoteDate.toISOString(),
      })

      flash(response.data.message || 'Bid submitted successfully.')

      setBidForm({
        freight_charges: '',
        origin_charges: '',
        destination_charges: '',
        transit_time_days: '5',
        quote_valid_until: '',
      })

      const [bidResponse, rankingResponse, eventResponse] = await Promise.all([
        api.get(`/bids/auctions/${selectedAuction}`),
        api.get(`/bids/auctions/${selectedAuction}/rankings`),
        api.get(`/bids/auctions/${selectedAuction}/events`),
      ])

      setBids(bidResponse.data)
      setRankings(rankingResponse.data)
      setEvents(eventResponse.data)
    } catch (err: any) {
      flash(errorMessage(err, 'Bid submission failed.'), true)
    } finally {
      setLoading(false)
    }
  }

  // Find the selected auction's details from already-loaded RFQs or invitations.
  const selectedAuctionData =
    rfqs.find((rfq) => rfq.auction?.id === selectedAuction)?.auction ||
    invitations.find((invitation) => invitation.auction?.id === selectedAuction)
      ?.auction

  const buyer = user?.role === 'BUYER'
  const supplier = user?.role === 'SUPPLIER'

  const activeRFQs = rfqs.filter(
    (rfq) => rfq.auction.status === 'ACTIVE',
  ).length

  const scheduledRFQs = rfqs.filter(
    (rfq) => rfq.auction.status === 'SCHEDULED',
  ).length

  if (!user) {
    return (
      <div className="login-page">
        <section className="login-visual">
          <div className="brand">
            <div className="brand-mark">G</div>
            <div className="brand-name">
              Go<span>Comet</span>
            </div>
          </div>

          <h1>Smarter freight procurement starts here.</h1>
          <p>
            Manage RFQs, run transparent British auctions and make better
            logistics decisions with real-time bidding.
          </p>

          <div style={{ marginTop: 38, color: '#62d9b2', fontSize: 12 }}>
            <ShieldCheck
              size={17}
              style={{ verticalAlign: 'middle', marginRight: 8 }}
            />
            Secure procurement workspace
          </div>
        </section>

        <section className="login-content">
          <form className="login-box" onSubmit={login}>
            <h2>Welcome back</h2>
            <p>Sign in to your GoComet workspace.</p>

            {error && <div className="notice error">{error}</div>}
            {success && <div className="notice success">{success}</div>}

            <div className="field">
              <label>Email address</label>
              <input
                name="email"
                type="email"
                placeholder="you@company.com"
                required
              />
            </div>

            <div className="field">
              <label>Password</label>
              <input
                name="password"
                type="password"
                placeholder="Enter your password"
                required
              />
            </div>

            <button className="btn btn-primary" disabled={loading}>
              {loading ? 'Signing in...' : 'Sign in to GoComet'}
            </button>

            <div className="login-foot">
              GoComet · Freight Procurement & Auction Platform
            </div>
          </form>
        </section>
      </div>
    )
  }

  const navItems =
    user.role === 'BUYER'
      ? [
          {
            id: 'dashboard',
            label: 'Overview',
            icon: ChartNoAxesCombined,
          },
          { id: 'rfqs', label: 'My RFQs', icon: ClipboardList },
          { id: 'create', label: 'Create RFQ', icon: Plus },
        ]
      : user.role === 'SUPPLIER'
        ? [
            {
              id: 'dashboard',
              label: 'Overview',
              icon: ChartNoAxesCombined,
            },
            { id: 'invitations', label: 'Invitations', icon: Bell },
          ]
        : [
            {
              id: 'dashboard',
              label: 'Overview',
              icon: ChartNoAxesCombined,
            },
          ]

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">G</div>
          <div className="brand-name">
            Go<span>Comet</span>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>

        {navItems.map((item) => {
          const Icon = item.icon

          return (
            <button
              key={item.id}
              className={`nav-item ${page === item.id ? 'active' : ''}`}
              onClick={() => {
                setPage(item.id)
                setSelectedAuction(null)
                flash('')
              }}
            >
              <Icon size={17} />
              <span>{item.label}</span>
            </button>
          )
        })}

        <div className="nav-label" style={{ marginTop: 25 }}>
          ACCOUNT
        </div>

        <button className="nav-item" onClick={loadDashboard}>
          <RefreshCw size={17} />
          <span>Refresh data</span>
        </button>

        <div className="sidebar-bottom">
          <div className="user-mini">
            <div className="avatar">{user.name.charAt(0).toUpperCase()}</div>
            <div>
              <strong>{user.name}</strong>
              <small>{user.role}</small>
            </div>
          </div>

          <button className="nav-item" onClick={logout}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace /{' '}
            <strong>
              {page === 'auction'
                ? 'Auction details'
                : page.startsWith('invite-')
                  ? 'Invite suppliers'
                  : page}
            </strong>
          </div>

          <div className="top-right">
            {page === 'auction' && (
              <span className="role-pill">
                {socketConnected ? (
                  <>
                    <Wifi size={13} /> Live
                  </>
                ) : (
                  <>
                    <WifiOff size={13} /> Reconnecting
                  </>
                )}
              </span>
            )}

            <span className="role-pill">{user.role}</span>
            <div className="avatar">{user.name.charAt(0).toUpperCase()}</div>
          </div>
        </header>

        <div className="page">
          {error && <div className="notice error">{error}</div>}
          {success && <div className="notice success">{success}</div>}

          {loading && <div className="notice">Loading data…</div>}

          {page === 'dashboard' && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Good day, {user.name.split(' ')[0]}</h1>
                  <p>
                    Here's what's happening in your procurement workspace.
                  </p>
                </div>

                {buyer && (
                  <button
                    className="btn btn-primary"
                    onClick={() => setPage('create')}
                  >
                    <Plus size={15} /> Create RFQ
                  </button>
                )}
              </div>

              <div className="stats-grid">
                {buyer ? (
                  <>
                    <Stat
                      title="Total RFQs"
                      value={rfqs.length}
                      icon={<ClipboardList size={17} />}
                      note="Created in your workspace"
                    />
                    <Stat
                      title="Active auctions"
                      value={activeRFQs}
                      icon={<Activity size={17} />}
                      note="Currently accepting bids"
                    />
                    <Stat
                      title="Scheduled"
                      value={scheduledRFQs}
                      icon={<Wallet size={17} />}
                      note="Waiting to start"
                    />
                    <Stat
                      title="Closed auctions"
                      value={
                        rfqs.filter((rfq) =>
                          ['CLOSED', 'FORCE_CLOSED'].includes(
                            rfq.auction.status,
                          ),
                        ).length
                      }
                      icon={<ShieldCheck size={17} />}
                      note="Auction completed"
                    />
                  </>
                ) : supplier ? (
                  <>
                    <Stat
                      title="Total invitations"
                      value={invitations.length}
                      icon={<Bell size={17} />}
                      note="Received from buyers"
                    />
                    <Stat
                      title="Awaiting response"
                      value={
                        invitations.filter((i) => i.status === 'INVITED')
                          .length
                      }
                      icon={<Activity size={17} />}
                      note="Pending your action"
                    />
                    <Stat
                      title="Accepted"
                      value={
                        invitations.filter((i) => i.status === 'ACCEPTED')
                          .length
                      }
                      icon={<Users size={17} />}
                      note="Ready to participate"
                    />
                    <Stat
                      title="Declined"
                      value={
                        invitations.filter((i) => i.status === 'DECLINED')
                          .length
                      }
                      icon={<ShieldCheck size={17} />}
                      note="Not participating"
                    />
                  </>
                ) : (
                  <>
                    <Stat
                      title="Platform access"
                      value="Admin"
                      icon={<ShieldCheck size={17} />}
                      note="Administrator account"
                    />
                    <Stat
                      title="User"
                      value={user.name}
                      icon={<Users size={17} />}
                      note="Signed in"
                    />
                  </>
                )}
              </div>

              {buyer ? (
                <RFQTable
                  rfqs={rfqs}
                  lowestBids={lowestBids}
                  onPublish={publishRFQ}
                  onOpen={openAuction}
                  onInvite={(id) => {
                    setPage(`invite-${id}`)
                    setInviteEmails('')
                  }}
                />
              ) : supplier ? (
                <InvitationTable
                  invitations={invitations}
                  onAction={invitationAction}
                  onOpen={openAuction}
                />
              ) : (
                <div className="panel">
                  <div className="empty">
                    Administrator workspace. User and platform administration
                    can be added here.
                  </div>
                </div>
              )}
            </>
          )}

          {page === 'rfqs' && buyer && (
            <>
              <div className="page-heading">
                <div>
                  <h1>My RFQs</h1>
                  <p>
                    Manage your requests for quotation and auctions.
                  </p>
                </div>

                <button
                  className="btn btn-primary"
                  onClick={() => setPage('create')}
                >
                  <Plus size={15} /> New RFQ
                </button>
              </div>

              <RFQTable
                rfqs={rfqs}
                lowestBids={lowestBids}
                onPublish={publishRFQ}
                onOpen={openAuction}
                onInvite={(id) => {
                  setPage(`invite-${id}`)
                  setInviteEmails('')
                }}
              />
            </>
          )}

          {page === 'create' && buyer && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Create a new RFQ</h1>
                  <p>
                    Configure your freight request and British auction
                    schedule.
                  </p>
                </div>
              </div>

              <form className="form-card" onSubmit={createRFQ}>
                <h2>RFQ information</h2>

                <div className="field">
                  <label>RFQ name *</label>
                  <input
                    name="name"
                    required
                    minLength={3}
                    maxLength={200}
                    placeholder="e.g. Delhi to Mumbai freight requirement"
                  />
                </div>

                <div className="field">
                  <label>Description</label>
                  <textarea
                    name="description"
                    maxLength={5000}
                    placeholder="Describe cargo, requirements and terms..."
                  />
                </div>

                <div className="form-grid">
                  <div className="field">
                    <label>Pickup date *</label>
                    <input name="pickup_date" type="date" required />
                  </div>

                  <div className="field">
                    <label>Service date *</label>
                    <input name="service_date" type="date" required />
                  </div>
                </div>

                <div className="section-title">Auction schedule</div>

                <div className="form-grid">
                  <div className="field">
                    <label>Start time *</label>
                    <input
                      name="start_time"
                      type="datetime-local"
                      required
                    />
                  </div>

                  <div className="field">
                    <label>Initial close time *</label>
                    <input
                      name="close_time"
                      type="datetime-local"
                      required
                    />
                  </div>

                  <div className="field">
                    <label>Forced close time *</label>
                    <input
                      name="forced_close_time"
                      type="datetime-local"
                      required
                    />
                  </div>

                  <div className="field">
                    <label>Extension trigger *</label>
                    <select name="trigger_type" required>
                      <option value="ANY_BID">Any valid bid</option>
                      <option value="ANY_RANK_CHANGE">
                        Any ranking change
                      </option>
                      <option value="L1_RANK_CHANGE">
                        L1 leader change
                      </option>
                    </select>
                  </div>

                  <div className="field">
                    <label>Trigger window (minutes) *</label>
                    <input
                      name="trigger_window_minutes"
                      type="number"
                      min="1"
                      max="1440"
                      defaultValue="2"
                      required
                    />
                  </div>

                  <div className="field">
                    <label>Extension duration (minutes) *</label>
                    <input
                      name="extension_minutes"
                      type="number"
                      min="1"
                      max="1440"
                      defaultValue="2"
                      required
                    />
                  </div>
                </div>

                <div className="notice">
                  The auction will never extend beyond the forced close time.
                  All times are interpreted in your local browser timezone and
                  sent to the server as UTC.
                </div>

                <button className="btn btn-primary" disabled={loading}>
                  <Plus size={15} />
                  {loading ? 'Creating…' : 'Create RFQ and auction'}
                </button>
              </form>
            </>
          )}

          {page.startsWith('invite-') && buyer && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Invite suppliers</h1>
                  <p>
                    Invite registered supplier accounts to participate in
                    this auction.
                  </p>
                </div>
              </div>

              <div className="form-card">
                <h2>Supplier email addresses</h2>

                <div className="field">
                  <label>
                    Email addresses (separate multiple addresses with commas
                    or new lines)
                  </label>
                  <textarea
                    value={inviteEmails}
                    onChange={(e) => setInviteEmails(e.target.value)}
                    placeholder="supplier1@company.com, supplier2@company.com"
                  />
                </div>

                <button
                  className="btn btn-primary"
                  disabled={loading}
                  onClick={() =>
                    inviteSuppliers(Number(page.replace('invite-', '')))
                  }
                >
                  <Send size={15} /> Send invitations
                </button>
              </div>
            </>
          )}

          {page === 'invitations' && supplier && (
            <>
              <div className="page-heading">
                <div>
                  <h1>My invitations</h1>
                  <p>Review RFQs shared with your company.</p>
                </div>
              </div>

              <InvitationTable
                invitations={invitations}
                onAction={invitationAction}
                onOpen={openAuction}
              />
            </>
          )}

          {page === 'auction' && (
            <>
              <div className="page-heading">
                <div>
                  <h1>Auction #{selectedAuction}</h1>
                  <p>
                    Live bidding, supplier rankings and auction activity.
                  </p>
                </div>

                <button
                  className="btn btn-secondary"
                  disabled={loading}
                  onClick={() =>
                    selectedAuction && openAuction(selectedAuction)
                  }
                >
                  <RefreshCw size={14} /> Refresh
                </button>
              </div>

              {selectedAuctionData && (
                <div className="detail-card auction-info">
                  <h3>
                    <Clock
                      size={15}
                      style={{ verticalAlign: 'middle', marginRight: 7 }}
                    />
                    Auction schedule and configuration
                  </h3>

                  <div className="auction-info-grid">
                    <InfoItem
                      label="Auction status"
                      value={selectedAuctionData.status.replaceAll('_', ' ')}
                    />
                    <InfoItem
                      label="Start time"
                      value={dateTime(selectedAuctionData.start_time)}
                    />
                    <InfoItem
                      label="Current close time"
                      value={dateTime(selectedAuctionData.close_time)}
                    />
                    <InfoItem
                      label="Forced close time"
                      value={dateTime(selectedAuctionData.forced_close_time)}
                    />
                    <InfoItem
                      label="Extension trigger"
                      value={triggerLabel(
                        selectedAuctionData.config?.trigger_type,
                      )}
                    />
                    <InfoItem
                      label="Trigger window"
                      value={`${selectedAuctionData.config?.trigger_window_minutes ?? '—'} minutes`}
                    />
                    <InfoItem
                      label="Extension duration"
                      value={`${selectedAuctionData.config?.extension_minutes ?? '—'} minutes`}
                    />
                    <InfoItem
                      label="Time remaining"
                      value={
                        <Countdown
                          closeTime={selectedAuctionData.close_time}
                        />
                      }
                    />
                  </div>
                </div>
              )}

              {!selectedAuctionData && (
                <div className="notice">
                  Auction schedule details are not available in the currently
                  loaded RFQ or invitation data.
                </div>
              )}

              <div className="detail-grid">
                <div className="detail-card">
                  <h3>
                    <ChartNoAxesCombined
                      size={15}
                      style={{ verticalAlign: 'middle', marginRight: 7 }}
                    />
                    Supplier rankings
                  </h3>

                  {rankings.length ? (
                    rankings.map((ranking) => (
                      <div className="detail-row" key={ranking.supplier_id}>
                        <span>
                          <b className="rank">L{ranking.rank}</b> · Supplier #
                          {ranking.supplier_id}
                        </span>
                        <strong>{money(ranking.total_price)}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="empty">No bids received yet.</div>
                  )}
                </div>

                <div className="detail-card">
                  <h3>
                    <Activity
                      size={15}
                      style={{ verticalAlign: 'middle', marginRight: 7 }}
                    />
                    Auction activity
                  </h3>

                  {events.length ? (
                    events.map((event) => (
                      <div className="detail-row" key={event.id}>
                        <span>
                          {event.event_type.replaceAll('_', ' ')}
                          <br />
                          <small>{dateTime(event.created_at)}</small>
                        </span>
                        <strong>{event.reason || '—'}</strong>
                      </div>
                    ))
                  ) : (
                    <div className="empty">No activity recorded.</div>
                  )}
                </div>
              </div>

              {supplier && (
                <form
                  className="form-card"
                  style={{ marginTop: 18 }}
                  onSubmit={submitBid}
                >
                  <h2>Submit a quotation</h2>

                  <div className="form-grid">
                    <div className="field">
                      <label>Freight charges (₹) *</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        required
                        value={bidForm.freight_charges}
                        onChange={(e) =>
                          setBidForm({
                            ...bidForm,
                            freight_charges: e.target.value,
                          })
                        }
                      />
                    </div>

                    <div className="field">
                      <label>Origin charges (₹) *</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        required
                        value={bidForm.origin_charges}
                        onChange={(e) =>
                          setBidForm({
                            ...bidForm,
                            origin_charges: e.target.value,
                          })
                        }
                      />
                    </div>

                    <div className="field">
                      <label>Destination charges (₹) *</label>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        required
                        value={bidForm.destination_charges}
                        onChange={(e) =>
                          setBidForm({
                            ...bidForm,
                            destination_charges: e.target.value,
                          })
                        }
                      />
                    </div>

                    <div className="field">
                      <label>Transit time (days) *</label>
                      <input
                        type="number"
                        min="0"
                        required
                        value={bidForm.transit_time_days}
                        onChange={(e) =>
                          setBidForm({
                            ...bidForm,
                            transit_time_days: e.target.value,
                          })
                        }
                      />
                    </div>

                    <div className="field">
                      <label>Quote valid until *</label>
                      <input
                        type="datetime-local"
                        required
                        value={bidForm.quote_valid_until}
                        onChange={(e) =>
                          setBidForm({
                            ...bidForm,
                            quote_valid_until: e.target.value,
                          })
                        }
                      />
                    </div>
                  </div>

                  <button className="btn btn-primary" disabled={loading}>
                    <Send size={14} /> Submit bid
                  </button>
                </form>
              )}

              <div className="panel" style={{ marginTop: 18 }}>
                <div className="panel-header">
                  <h2>Bid history</h2>
                  <span>{bids.length} bids</span>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Bid ID</th>
                        <th>Supplier</th>
                        <th>Freight</th>
                        <th>Origin</th>
                        <th>Destination</th>
                        <th>Total price</th>
                        <th>Transit</th>
                        <th>Quote validity</th>
                        <th>Submitted</th>
                      </tr>
                    </thead>

                    <tbody>
                      {bids.map((bid) => (
                        <tr key={bid.id}>
                          <td>#{bid.id}</td>
                          <td>Supplier #{bid.supplier_id}</td>
                          <td>{money(bid.freight_charges)}</td>
                          <td>{money(bid.origin_charges)}</td>
                          <td>{money(bid.destination_charges)}</td>
                          <td className="primary-cell">
                            {money(bid.total_price)}
                          </td>
                          <td>{bid.transit_time_days} days</td>
                          <td>{dateTime(bid.quote_valid_until)}</td>
                          <td>{dateTime(bid.submitted_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {!bids.length && (
                    <div className="empty">
                      No bids have been submitted for this auction.
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </main>
    </div>
  )
}

function InfoItem({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="info-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function Stat({
  title,
  value,
  icon,
  note,
}: {
  title: string
  value: string | number
  icon: React.ReactNode
  note: string
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{title}</span>
        <div className="stat-icon">{icon}</div>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note}</div>
    </div>
  )
}

function RFQTable({
  rfqs,
  lowestBids,
  onPublish,
  onOpen,
  onInvite,
}: {
  rfqs: RFQ[]
  lowestBids: Record<number, number>
  onPublish: (id: number) => void
  onOpen: (id: number) => void
  onInvite: (id: number) => void
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>RFQ & auction overview</h2>
        <span>{rfqs.length} records</span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>RFQ</th>
              <th>Pickup</th>
              <th>Lowest bid</th>
              <th>Auction status</th>
              <th>Current close</th>
              <th>Forced close</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {rfqs.map((rfq) => (
              <tr key={rfq.id}>
                <td>
                  <div className="primary-cell">{rfq.name}</div>
                  <small className="muted">{rfq.reference_id}</small>
                </td>

                <td>{rfq.pickup_date}</td>

                <td className="primary-cell">
                  {lowestBids[rfq.auction.id] !== undefined
                    ? money(lowestBids[rfq.auction.id])
                    : 'No bids'}
                </td>

                <td>
                  <span className={statusClass(rfq.auction.status)}>
                    {rfq.auction.status.replaceAll('_', ' ')}
                  </span>
                </td>

                <td>{dateTime(rfq.auction.close_time)}</td>
                <td>{dateTime(rfq.auction.forced_close_time)}</td>

                <td>
                  <div className="actions">
                    <button
                      className="small-btn"
                      onClick={() => onOpen(rfq.auction.id)}
                    >
                      Details
                    </button>

                    {rfq.status === 'DRAFT' && (
                      <button
                        className="small-btn"
                        onClick={() => onPublish(rfq.id)}
                      >
                        Publish
                      </button>
                    )}

                    <button
                      className="small-btn"
                      onClick={() => onInvite(rfq.id)}
                    >
                      Invite
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!rfqs.length && (
          <div className="empty">
            No RFQs yet. Create your first RFQ to get started.
          </div>
        )}
      </div>
    </div>
  )
}

function InvitationTable({
  invitations,
  onAction,
  onOpen,
}: {
  invitations: Invitation[]
  onAction: (id: number, action: 'accept' | 'decline') => void
  onOpen: (id: number) => void
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Supplier invitations</h2>
        <span>{invitations.length} invitations</span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>RFQ</th>
              <th>Reference</th>
              <th>Buyer</th>
              <th>Invited</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>

          <tbody>
            {invitations.map((invitation) => (
              <tr key={invitation.participant_id}>
                <td className="primary-cell">{invitation.rfq_name}</td>
                <td>{invitation.rfq_reference_id}</td>
                <td>{invitation.buyer_name}</td>
                <td>{dateTime(invitation.invited_at)}</td>

                <td>
                  <span className={statusClass(invitation.status)}>
                    {invitation.status}
                  </span>
                </td>

                <td>
                  <div className="actions">
                    {invitation.status === 'INVITED' && (
                      <>
                        <button
                          className="small-btn"
                          onClick={() =>
                            onAction(invitation.participant_id, 'accept')
                          }
                        >
                          Accept
                        </button>

                        <button
                          className="small-btn"
                          onClick={() =>
                            onAction(invitation.participant_id, 'decline')
                          }
                        >
                          Decline
                        </button>
                      </>
                    )}

                    {invitation.status === 'ACCEPTED' &&
                      invitation.auction?.id && (
                        <button
                          className="small-btn"
                          onClick={() => onOpen(invitation.auction!.id)}
                        >
                          Open auction
                        </button>
                      )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!invitations.length && (
          <div className="empty">
            You don't have any invitations yet.
          </div>
        )}
      </div>
    </div>
  )
}

export default App
